"""Portfolio intelligence: risk analytics + rule-based attention alerts.

Everything here is deterministic math over data already fetched by
market_data — no extra network calls beyond one SPY benchmark fetch for beta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models.schemas import (
    PortfolioAlert,
    PortfolioInsights,
    RiskMetrics,
    StockReport,
)
from . import market_data, screener
from . import portfolio as pf_service

RISK_FREE_RATE = 0.04
BENCHMARK = "SPY"

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "opportunity": 2}


# ------------------------------------------------------------------ risk math
def _daily_close(md) -> pd.Series:
    """Close series with a tz-naive, normalized date index.

    Live yfinance frames are tz-aware, mock frames are naive — normalizing both
    lets holdings and the SPY benchmark align on a shared calendar.
    """
    close = md.history["Close"].copy()
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    close.index = idx.normalize()
    return close[~close.index.duplicated(keep="last")]


def _portfolio_value_series() -> pd.Series:
    """Unrounded daily portfolio value: sum of shares * close per holding."""
    pf = pf_service.load_portfolio()
    per_symbol: dict[str, pd.Series] = {}
    for h in pf.get("holdings", []):
        shares = float(h.get("shares", 0) or 0)
        if shares <= 0:
            continue
        try:
            md = market_data.get_market_data(h["symbol"])
        except Exception:
            continue
        per_symbol[h["symbol"].upper()] = _daily_close(md) * shares
    if not per_symbol:
        return pd.Series(dtype=float)
    # concat unions the date indexes; column-by-column assignment would silently
    # truncate everything to the FIRST symbol's calendar.
    frame = pd.concat(per_symbol, axis=1).sort_index().ffill()
    # Drop leading days where newer listings have no data yet — a NaN->0 there
    # would read as a fake drawdown/spike in the combined series.
    return frame.dropna().sum(axis=1)


def _returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def _beta(port_returns: pd.Series) -> float | None:
    try:
        md = market_data.get_market_data(BENCHMARK)
    except Exception:
        return None
    bench_ret = _returns(_daily_close(md))
    joined = pd.concat([port_returns, bench_ret], axis=1, join="inner").dropna()
    joined = joined.tail(126)  # ~6 months
    if len(joined) < 20:
        return None
    p, b = joined.iloc[:, 0], joined.iloc[:, 1]
    var = float(b.var())
    if var == 0:
        return None
    return round(float(p.cov(b) / var), 2)


def compute_risk(reports: list[StockReport]) -> RiskMetrics:
    metrics = RiskMetrics()

    held = [r for r in reports if r.market_value]
    total = sum(r.market_value or 0 for r in held)
    if held and total > 0:
        weights = sorted(
            ((r.symbol, (r.market_value or 0) / total * 100) for r in held),
            key=lambda x: x[1],
            reverse=True,
        )
        metrics.top_symbol = weights[0][0]
        metrics.top_weight_pct = round(weights[0][1], 1)
        metrics.top5_weight_pct = round(sum(w for _, w in weights[:5]), 1)

    values = _portfolio_value_series().tail(252)
    if len(values) >= 20:
        rets = _returns(values)
        std = float(rets.std())
        mean = float(rets.mean())
        metrics.volatility_pct = round(std * np.sqrt(252) * 100, 1)
        if std > 0:
            metrics.sharpe = round(
                (mean * 252 - RISK_FREE_RATE) / (std * np.sqrt(252)), 2
            )
        drawdown = values / values.cummax() - 1
        metrics.max_drawdown_pct = round(float(drawdown.min()) * 100, 1)

        best_idx, worst_idx = rets.idxmax(), rets.idxmin()
        metrics.best_day_pct = round(float(rets.max()) * 100, 2)
        metrics.best_day_date = pd.Timestamp(best_idx).strftime("%Y-%m-%d")
        metrics.worst_day_pct = round(float(rets.min()) * 100, 2)
        metrics.worst_day_date = pd.Timestamp(worst_idx).strftime("%Y-%m-%d")

        metrics.beta = _beta(rets)

    return metrics


# --------------------------------------------------------------- alert rules
def _stock_alerts(r: StockReport, weight_pct: float | None) -> list[PortfolioAlert]:
    alerts: list[PortfolioAlert] = []
    i = r.indicators
    chg = r.quote.change_pct
    held = r.market_value is not None

    def add(severity: str, label: str, detail: str):
        alerts.append(PortfolioAlert(
            symbol=r.symbol, severity=severity, label=label, detail=detail))

    if chg <= -5:
        add("critical", "Sharp drop", f"Down {abs(chg):.1f}% today")
    elif chg >= 5:
        add("opportunity", "Big up day", f"Up {chg:.1f}% today")

    if held and r.unrealized_pl_pct is not None:
        if r.unrealized_pl_pct <= -20:
            add("critical", "Deep drawdown",
                f"Position {r.unrealized_pl_pct:.1f}% below cost — reassess the thesis")
        elif r.unrealized_pl_pct <= -10:
            add("warning", "Position underwater",
                f"Position {r.unrealized_pl_pct:.1f}% below cost")

    if i.rsi is not None:
        if i.rsi >= 75:
            add("warning", "Overbought", f"RSI {i.rsi:.0f} — extended, pullback risk")
        elif i.rsi <= 30:
            add("opportunity", "Oversold", f"RSI {i.rsi:.0f} — mean-reversion zone")

    if (held and i.sma50 and i.sma200 and i.sma50 < i.sma200
            and r.quote.price < i.sma200):
        add("warning", "Below long-term trend",
            "Price under the 200-day with a death-cross regime")

    if i.pct_from_52w_high is not None and i.pct_from_52w_high >= -2:
        add("opportunity", "52w-high zone",
            f"Within {abs(i.pct_from_52w_high):.1f}% of the 52-week high")

    if i.volume_ratio is not None and i.volume_ratio >= 2:
        if chg >= 0:
            add("opportunity", "Volume-backed move",
                f"Volume {i.volume_ratio:.1f}x average on an up day")
        else:
            add("warning", "Heavy selling volume",
                f"Volume {i.volume_ratio:.1f}x average on a down day")

    score = screener.breakout_score(i, r.quote)
    if score >= 70:
        add("opportunity", "Breakout setup", f"Breakout readiness {score:.0f}/100")

    if weight_pct is not None and weight_pct > 25:
        add("warning", "Concentration risk",
            f"{weight_pct:.0f}% of the portfolio is in this one name")

    return alerts


def build_alerts(reports: list[StockReport]) -> list[PortfolioAlert]:
    held_total = sum(r.market_value or 0 for r in reports)
    alerts: list[PortfolioAlert] = []
    for r in reports:
        weight = (
            (r.market_value or 0) / held_total * 100
            if held_total and r.market_value else None
        )
        alerts.extend(_stock_alerts(r, weight))
    alerts.sort(key=lambda a: (_SEVERITY_ORDER.get(a.severity, 9), a.symbol))
    return alerts


def portfolio_insights(reports: list[StockReport] | None = None) -> PortfolioInsights:
    if reports is None:
        _, held = pf_service.portfolio_summary()
        reports = held + pf_service.watchlist_reports()
    source = "mock" if any(r.quote.source == "mock" for r in reports) else "live"
    return PortfolioInsights(
        source=source,
        risk=compute_risk(reports),
        alerts=build_alerts(reports),
    )
