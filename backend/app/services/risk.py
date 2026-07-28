"""Risk desk — the decision layer on top of the risk measurements.

`insights.compute_risk` already measures the book (beta, volatility, Sharpe,
max drawdown, concentration). This module answers the questions that actually
gate a trade:

  01 POSITION SIZE   how much, given the stop distance and the risk budget
  02 STOP LOSS       where the exit is, defined BEFORE entry
  03 DAILY LIMITS    how much can be lost today before trading stops
  04 PORTFOLIO RISK  total open risk across every position, plus correlation
  05 ALLOCATION      how much of the book is deployed

Sizing is risk-based, not conviction-based: you risk a fixed slice of equity
per trade, so a volatile name with a wide stop gets a SMALLER position than a
quiet one. That is the whole point — it equalizes the damage a wrong call can
do, instead of equalizing the dollars.

Nothing here fabricates a number. VaR and correlation need a real sample; when
the book is too young the field stays None and `notes` says why.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import settings
from ..models.schemas import (
    PositionPlan,
    PositionRisk,
    RiskDesk,
    StockReport,
)
from . import insights, market_data, portfolio as pf_service


# --------------------------------------------------------------- stop levels
def stop_for(report: StockReport) -> tuple[float | None, str | None]:
    """Where the exit goes, and why.

    Two candidates: a volatility stop (N x ATR below price) and the 200-day.
    We take whichever is CLOSER to price — the tighter of the two — because a
    stop further away than the trend break is not protecting anything.
    """
    ind = report.indicators
    price = report.quote.price
    if not price or price <= 0:
        return None, None

    candidates: list[tuple[float, str]] = []
    if ind.atr and ind.atr > 0:
        candidates.append(
            (price - settings.STOP_ATR_MULT * ind.atr,
             f"{settings.STOP_ATR_MULT:g}x ATR")
        )
    # Only useful as a stop when it sits below price; above price it's a target.
    if ind.sma200 and 0 < ind.sma200 < price:
        candidates.append((ind.sma200, "200-day"))

    valid = [(lvl, why) for lvl, why in candidates if lvl > 0]
    if not valid:
        return None, None
    lvl, why = max(valid, key=lambda c: c[0])   # closest below price = highest
    return round(lvl, 2), why


# ------------------------------------------------------------ position sizing
def plan_for(report: StockReport, equity: float, cash: float | None = None) -> PositionPlan:
    """Pre-trade sizing for one candidate.

    Risk budget = equity * RISK_PER_TRADE_PCT. Shares = budget / risk-per-share.
    Then two caps apply: never exceed MAX_POSITION_PCT of the book, and never
    size past available dry powder.
    """
    price = report.quote.price
    stop, basis = stop_for(report)
    plan = PositionPlan(symbol=report.symbol, price=price, stop=stop, stop_basis=basis)

    if not price or price <= 0 or equity <= 0:
        plan.note = "No live price — cannot size."
        return plan

    budget = equity * settings.RISK_PER_TRADE_PCT / 100.0
    if stop is None or stop >= price:
        plan.note = (
            "No usable stop (needs ATR or a 200-day below price) — "
            "size manually and set an exit before entering."
        )
        return plan

    risk_per_share = price - stop
    plan.risk_per_share = round(risk_per_share, 2)

    dollars = (budget / risk_per_share) * price
    max_dollars = equity * settings.MAX_POSITION_PCT / 100.0
    if dollars > max_dollars:
        dollars = max_dollars
        plan.capped_by = "max position"
    if cash is not None and dollars > cash:
        dollars = max(0.0, cash)
        plan.capped_by = "dry powder"

    plan.dollars = round(dollars, 2)
    plan.shares = round(dollars / price, 4)          # fractional shares are available
    plan.pct_of_equity = round(dollars / equity * 100, 2) if equity else 0.0
    plan.risk_amount = round(plan.shares * risk_per_share, 2)

    stop_pct = risk_per_share / price * 100
    plan.note = (
        f"Stop ${stop:,.2f} ({basis}, {stop_pct:.1f}% below). "
        f"Risking {settings.RISK_PER_TRADE_PCT:g}% of equity "
        f"(${plan.risk_amount:,.0f}) buys ${plan.dollars:,.0f}"
        + (f" — capped by {plan.capped_by}." if plan.capped_by else ".")
    )
    return plan


# -------------------------------------------------------------- correlation
def _returns_frame(symbols: list[str], lookback: int = 126) -> pd.DataFrame:
    """Aligned daily-return columns for the given symbols (inner join)."""
    cols: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            md = market_data.get_market_data(sym)
        except Exception:
            continue
        close = insights._daily_close(md)
        if len(close) > 5:
            cols[sym.upper()] = close.pct_change()
    if len(cols) < 2:
        return pd.DataFrame()
    return pd.concat(cols, axis=1).dropna().tail(lookback)


def _avg_pairwise_correlation(frame: pd.DataFrame) -> float | None:
    """Mean off-diagonal correlation — how much the book moves as one thing."""
    if frame.shape[1] < 2 or len(frame) < settings.RISK_MIN_DAYS:
        return None
    corr = frame.corr().to_numpy()
    n = corr.shape[0]
    off = corr[~np.eye(n, dtype=bool)]
    off = off[np.isfinite(off)]
    return round(float(off.mean()), 2) if off.size else None


# ---------------------------------------------------------------- liquidity
def _liquidity(reports: list[StockReport]) -> str | None:
    """Dollar-volume proxy: can these positions be exited without moving price?"""
    vols = []
    for r in reports:
        vol = r.quote.volume
        if vol and r.quote.price:
            vols.append(vol * r.quote.price)
    if not vols:
        return None
    median = float(np.median(vols))
    if median >= 100_000_000:
        return "HIGH"
    if median >= 10_000_000:
        return "MEDIUM"
    return "LOW"


# ------------------------------------------------------------------- the desk
def risk_desk() -> RiskDesk:
    summary, held = pf_service.portfolio_summary()

    equity = summary.total_market_value or 0.0
    cash = summary.cash or 0.0
    invested = max(0.0, equity - cash)
    notes: list[str] = []

    metrics = insights.compute_risk(held)

    # ---- 04: per-position open risk (entry -> stop) ------------------------
    positions: list[PositionRisk] = []
    total_risk = 0.0
    unstopped: list[str] = []
    for r in held:
        mv = r.market_value or 0.0
        if mv <= 0:
            continue
        weight = mv / equity * 100 if equity else 0.0
        stop, basis = stop_for(r)
        pr = PositionRisk(
            symbol=r.symbol,
            price=r.quote.price,
            market_value=round(mv, 2),
            weight_pct=round(weight, 1),
            stop=stop,
            stop_basis=basis,
            over_size=weight > settings.MAX_POSITION_PCT,
        )
        if stop and r.quote.price and stop < r.quote.price:
            dist = (r.quote.price - stop) / r.quote.price
            risk_amt = mv * dist
            pr.stop_distance_pct = round(dist * 100, 1)
            pr.risk_amount = round(risk_amt, 2)
            pr.risk_pct_of_equity = round(risk_amt / equity * 100, 2) if equity else None
            total_risk += risk_amt
        else:
            unstopped.append(r.symbol)
        positions.append(pr)
    positions.sort(key=lambda p: -(p.risk_amount or 0))

    if unstopped:
        notes.append(
            f"No stop level derivable for {', '.join(unstopped)} — "
            "excluded from portfolio risk, so the true figure is higher."
        )

    # ---- 03: daily loss limit --------------------------------------------
    limit_amount = equity * settings.DAILY_LOSS_LIMIT_PCT / 100.0
    day_pl = summary.day_change or 0.0
    breached = day_pl < 0 and abs(day_pl) >= limit_amount and limit_amount > 0

    # ---- 05: VaR + correlation, gated on a real sample --------------------
    values = insights._portfolio_value_series().tail(252)
    history_days = len(values)
    var_pct = var_amt = None
    if history_days >= settings.RISK_MIN_DAYS:
        rets = insights._returns(values)
        if len(rets) >= settings.RISK_MIN_DAYS:
            var_pct = round(float(np.percentile(rets, 5)) * 100, 2)
            var_amt = round(equity * var_pct / 100, 2)
    else:
        notes.append(
            f"Value-at-risk needs {settings.RISK_MIN_DAYS} sessions of book "
            f"history; there are {history_days}. Reported once the sample is real."
        )

    symbols = [r.symbol for r in held if (r.market_value or 0) > 0]
    frame = _returns_frame(symbols)
    avg_corr = _avg_pairwise_correlation(frame)
    if avg_corr is None and len(symbols) >= 2:
        notes.append(
            f"Correlation needs {settings.RISK_MIN_DAYS} overlapping sessions "
            "across holdings; not enough shared history yet."
        )

    # ---- status ----------------------------------------------------------
    risk_pct = round(total_risk / equity * 100, 2) if equity else None
    over = [p.symbol for p in positions if p.over_size]
    if over:
        notes.append(
            f"{', '.join(over)} exceeds the {settings.MAX_POSITION_PCT:g}% "
            "single-position cap — one name can set the whole month."
        )

    if breached:
        status = "BREACHED"
    elif over or (risk_pct is not None and risk_pct > settings.DAILY_LOSS_LIMIT_PCT * 2):
        status = "ELEVATED"
    else:
        status = "PROTECTED"

    return RiskDesk(
        equity=round(equity, 2),
        invested=round(invested, 2),
        cash=round(cash, 2),
        status=status,
        risk_per_trade_pct=settings.RISK_PER_TRADE_PCT,
        risk_budget_amount=round(equity * settings.RISK_PER_TRADE_PCT / 100, 2),
        daily_loss_limit_pct=settings.DAILY_LOSS_LIMIT_PCT,
        daily_loss_limit_amount=round(limit_amount, 2),
        day_pl=round(day_pl, 2),
        day_pl_pct=round(summary.day_change_pct or 0.0, 2),
        limit_breached=breached,
        portfolio_risk_pct=risk_pct,
        portfolio_risk_amount=round(total_risk, 2),
        exposure_utilization_pct=round(invested / equity * 100, 1) if equity else 0.0,
        positions=positions,
        max_drawdown_pct=metrics.max_drawdown_pct,
        var95_pct=var_pct,
        var95_amount=var_amt,
        beta=metrics.beta,
        avg_correlation=avg_corr,
        liquidity=_liquidity(held),
        history_days=history_days,
        notes=notes,
        metrics=metrics,
        source=summary.source,
    )


def facts_block() -> str:
    """Compact risk summary for injection into advisor / debate prompts."""
    try:
        d = risk_desk()
    except Exception:
        return ""
    lines = [
        "RISK DESK (deterministic, from the live book):",
        f"- Equity ${d.equity:,.0f} | invested ${d.invested:,.0f} | "
        f"dry powder ${d.cash:,.0f} ({d.exposure_utilization_pct:.0f}% deployed)",
        f"- Risk budget per new trade: {d.risk_per_trade_pct:g}% "
        f"= ${d.risk_budget_amount:,.0f}",
        f"- Daily loss limit {d.daily_loss_limit_pct:g}% "
        f"(${d.daily_loss_limit_amount:,.0f}); today {d.day_pl:+,.0f}"
        + (" — LIMIT BREACHED, no new risk today." if d.limit_breached else ""),
        f"- Status {d.status}",
    ]
    if d.portfolio_risk_pct is not None:
        lines.append(
            f"- Total open risk to stops: {d.portfolio_risk_pct:.2f}% of equity "
            f"(${d.portfolio_risk_amount:,.0f})"
        )
    if d.avg_correlation is not None:
        lines.append(
            f"- Average pairwise correlation {d.avg_correlation:.2f} "
            "(high means the book is really one bet)"
        )
    if d.var95_pct is not None:
        lines.append(f"- 1-day VaR(95): {d.var95_pct:.2f}% (${d.var95_amount:,.0f})")
    for n in d.notes:
        lines.append(f"- NOTE: {n}")
    return "\n".join(lines)
