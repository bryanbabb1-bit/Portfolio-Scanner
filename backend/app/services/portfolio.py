"""Portfolio + report assembly."""
from __future__ import annotations

import json
import math
import os
import tempfile

import pandas as pd


def _num(x) -> float:
    """Coerce None/NaN/inf to 0.0. Note `nan or 0` == nan (NaN is truthy), so
    plain `x or 0` does NOT guard NaN — a single NaN quote would otherwise
    poison a sum and make the whole response non-JSON-compliant (500)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0

from ..config import settings
from ..models.schemas import (
    Candle,
    PortfolioHistory,
    PortfolioSummary,
    PriceHistory,
    StockReport,
    ValuePoint,
)
from . import market_data
from .technical import build_quote, compute_indicators, derive_signals


def _auto_theme(symbol: str, manual: str | None) -> str:
    from . import themes  # local import — themes reaches back to this module
    return themes.resolve(symbol, manual)


def load_portfolio() -> dict:
    with open(settings.PORTFOLIO_FILE) as f:
        return json.load(f)


def _dedupe(cfg: dict) -> dict:
    """Drop watchlist entries for names already held.

    Once a watched name is bought it is tracked as a holding, so leaving it on
    the watchlist double-counts it in every scan and reads as a separate
    interest. That happened naturally here: activating a rebalance plan
    watchlisted its targets, and buying them left both records behind. Enforced
    on save so it cannot drift back rather than being cleaned by hand.
    """
    held = {str(h.get("symbol", "")).upper()
            for h in cfg.get("holdings", []) if h.get("symbol")}
    watch = cfg.get("watchlist")
    if isinstance(watch, list) and held:
        cfg["watchlist"] = [
            w for w in watch
            if str(w.get("symbol", "")).upper() not in held
        ]
    return cfg


def save_portfolio(cfg: dict) -> dict:
    """Atomically persist the portfolio config to disk and return it.

    Writes to a temp file in the same directory then os.replace() so a crash
    mid-write can never leave a half-written portfolio.json behind.
    """
    cfg = _dedupe(cfg)
    path = settings.PORTFOLIO_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return cfg


def _holding_map() -> dict[str, dict]:
    pf = load_portfolio()
    return {h["symbol"].upper(): h for h in pf.get("holdings", [])}


def build_report(symbol: str, theme: str | None = None) -> StockReport:
    md = market_data.get_market_data(symbol)
    ind = compute_indicators(md.history)
    quote = build_quote(md, ind)
    signals = derive_signals(quote, ind)

    # Analyst view with computed upside.
    a = md.analyst or {}
    upside = None
    if a.get("mean_target") and quote.price:
        upside = round((a["mean_target"] / quote.price - 1) * 100, 2)
    from ..models.schemas import AnalystView, NewsItem

    analyst = AnalystView(
        recommendation=a.get("recommendation"),
        mean_target=a.get("mean_target"),
        high_target=a.get("high_target"),
        low_target=a.get("low_target"),
        num_analysts=a.get("num_analysts"),
        upside_pct=upside,
    )
    news = [NewsItem(**n) for n in (md.news or [])[:8]]

    # ~30-point recent close series for an inline card sparkline.
    closes = md.history["Close"].tail(30)
    spark = [round(float(c), 2) for c in closes.tolist()]

    days_to_earnings = None
    if md.earnings_date:
        try:
            delta = (pd.Timestamp(md.earnings_date).date()
                     - pd.Timestamp.now().date()).days
            days_to_earnings = delta if delta >= 0 else None
        except (ValueError, TypeError):
            pass

    report = StockReport(
        symbol=md.symbol,
        theme=theme,
        quote=quote,
        indicators=ind,
        analyst=analyst,
        news=news,
        signals=signals,
        spark=spark,
        earnings_date=md.earnings_date,
        days_to_earnings=days_to_earnings,
    )

    # Attach position economics if held.
    held = _holding_map().get(md.symbol)
    if held:
        shares = float(held.get("shares", 0))
        cost = float(held.get("cost_basis", 0))
        mv = round(shares * quote.price, 2)
        cost_total = shares * cost
        report.shares = shares
        report.cost_basis = cost
        report.market_value = mv
        report.unrealized_pl = round(mv - cost_total, 2)
        report.unrealized_pl_pct = round(
            ((quote.price / cost - 1) * 100) if cost else 0.0, 2
        )
        if not report.theme:
            report.theme = held.get("theme")
    if not report.theme:
        report.theme = _auto_theme(md.symbol, None)
    return report


def portfolio_summary() -> tuple[PortfolioSummary, list[StockReport]]:
    pf = load_portfolio()
    holdings = pf.get("holdings", [])
    try:
        from . import journal
        journal.snapshot_and_diff(holdings)  # capture trades since last read
    except Exception as exc:
        print(f"[portfolio] journal diff failed: {exc!r}")
    market_data.warm_cache([h["symbol"] for h in holdings])
    reports: list[StockReport] = []
    for h in holdings:
        reports.append(build_report(h["symbol"], h.get("theme")))

    # Uninvested cash (buying power) counts toward the account total and the
    # allocation, but is never quoted/charted/scanned — it's just a number.
    cash = _num(pf.get("cash", 0))
    positions_mv = sum(_num(r.market_value) for r in reports)
    total_mv = positions_mv + cash
    total_cost = sum(_num(r.cost_basis) * _num(r.shares) for r in reports)
    total_pl = positions_mv - total_cost      # cash has no P/L
    day_change = sum(_num(r.quote.change) * _num(r.shares) for r in reports)
    prev_value = total_mv - day_change        # yesterday's account value (incl. cash)

    by_theme: dict[str, float] = {}
    for r in reports:
        by_theme[r.theme or "Other"] = round(
            by_theme.get(r.theme or "Other", 0) + (r.market_value or 0), 2
        )
    if cash:
        by_theme["Cash & Income"] = round(by_theme.get("Cash & Income", 0) + cash, 2)

    # Realized P/L — booked gains/losses from positions already closed/trimmed.
    realized = 0.0
    try:
        from . import journal
        realized = journal.realized_total()
    except Exception:
        realized = 0.0
    total_return = total_pl + realized  # unrealized + realized = real "how I'm doing"

    source = "mock" if any(r.quote.source == "mock" for r in reports) else "live"
    summary = PortfolioSummary(
        total_market_value=round(total_mv, 2),
        total_cost=round(total_cost, 2),
        total_unrealized_pl=round(total_pl, 2),
        total_unrealized_pl_pct=round((total_pl / total_cost * 100) if total_cost else 0, 2),
        day_change=round(day_change, 2),
        day_change_pct=round((day_change / prev_value * 100) if prev_value else 0, 2),
        positions=len(reports),
        cash=round(cash, 2),
        source=source,
        by_theme=by_theme,
        realized_pl=round(realized, 2),
        total_return=round(total_return, 2),
        total_return_pct=round((total_return / total_cost * 100) if total_cost else 0, 2),
    )
    return summary, reports


def watchlist_reports() -> list[StockReport]:
    """Report cards for watched (non-held) names, de-duped against holdings."""
    pf = load_portfolio()
    held = {h["symbol"].upper() for h in pf.get("holdings", [])}
    market_data.warm_cache(
        [w["symbol"] for w in pf.get("watchlist", [])
         if w["symbol"].upper() not in held]
    )
    reports: list[StockReport] = []
    seen: set[str] = set()
    for item in pf.get("watchlist", []):
        sym = item["symbol"].upper()
        if sym in held or sym in seen:
            continue
        seen.add(sym)
        reports.append(build_report(sym, item.get("theme")))
    return reports


# ------------------------------------------------------------------ charting
_RANGE_POINTS = {"1mo": 22, "3mo": 66, "6mo": 132, "1y": 260}
_INTRADAY_RANGES = {"1d", "5d"}


def _intraday_price_history(symbol: str, range_: str) -> PriceHistory:
    from .technical import _rsi

    df, source = market_data.get_intraday(symbol, range_)
    close = df["Close"]
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    rsi = _rsi(close)
    candles: list[Candle] = []
    for idx, row in df.iterrows():
        ts = pd.Timestamp(idx)
        v20, v50, vr = sma20.get(idx), sma50.get(idx), rsi.get(idx)
        candles.append(Candle(
            date=ts.strftime("%Y-%m-%d %H:%M"),
            open=round(float(row["Open"]), 2),
            high=round(float(row["High"]), 2),
            low=round(float(row["Low"]), 2),
            close=round(float(row["Close"]), 2),
            volume=float(row["Volume"]),
            sma20=None if v20 is None or pd.isna(v20) else round(float(v20), 2),
            sma50=None if v50 is None or pd.isna(v50) else round(float(v50), 2),
            rsi=None if vr is None or pd.isna(vr) else round(float(vr), 1),
        ))
    return PriceHistory(symbol=symbol.upper(), range=range_, source=source,
                        candles=candles)


def price_history(symbol: str, range_: str = "6mo") -> PriceHistory:
    """OHLCV candles + SMA20/50 overlays for charting a single symbol.

    Daily bars for 1mo..1y; intraday bars (5-min / 30-min) for 1d / 5d, where
    the SMAs are computed over intraday bars instead."""
    if range_ in _INTRADAY_RANGES:
        return _intraday_price_history(symbol, range_)
    from .technical import _rsi

    md = market_data.get_market_data(symbol)
    hist = md.history
    close = hist["Close"]
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    rsi = _rsi(close)

    points = _RANGE_POINTS.get(range_, _RANGE_POINTS["6mo"])
    tail = hist.tail(points)
    s20 = sma20.tail(points)
    s50 = sma50.tail(points)
    r = rsi.tail(points)

    candles: list[Candle] = []
    for idx, row in tail.iterrows():
        ts = pd.Timestamp(idx)
        v20 = s20.get(idx)
        v50 = s50.get(idx)
        vr = r.get(idx)
        candles.append(
            Candle(
                date=ts.strftime("%Y-%m-%d"),
                open=round(float(row["Open"]), 2),
                high=round(float(row["High"]), 2),
                low=round(float(row["Low"]), 2),
                close=round(float(row["Close"]), 2),
                volume=float(row["Volume"]),
                sma20=None if v20 is None or pd.isna(v20) else round(float(v20), 2),
                sma50=None if v50 is None or pd.isna(v50) else round(float(v50), 2),
                rsi=None if vr is None or pd.isna(vr) else round(float(vr), 1),
            )
        )
    return PriceHistory(
        symbol=md.symbol, range=range_, source=md.source, candles=candles
    )


def _prior_session_close(md) -> tuple[float, str] | None:
    """Prior-session close for `md`, plus its date label ("YYYY-MM-DD 16:00").

    Returns the SAME baseline build_quote() uses for today's change, so a 1d
    chart anchored on this matches the hero's "Today" number exactly. Mirrors
    build_quote: if today's bar already exists, the prior close is the bar
    BEFORE it; otherwise the last completed bar IS the prior close.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    close = md.history["Close"].dropna()
    if len(close) == 0:
        return None
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    has_today = str(close.index[-1])[:10] == today
    if has_today and len(close) > 1:
        prev, prev_idx = float(close.iloc[-2]), close.index[-2]
    else:
        prev, prev_idx = float(close.iloc[-1]), close.index[-1]
    return prev, pd.Timestamp(prev_idx).strftime("%Y-%m-%d 16:00")


def portfolio_history(range_: str = "6mo") -> PortfolioHistory:
    """Aggregate portfolio market value over time.

    For each holding, value = shares * daily close. Series are aligned on a
    common date index (outer join, forward-filled) then summed, so names with
    different history lengths still combine cleanly.
    """
    pf = load_portfolio()
    holdings = pf.get("holdings", [])
    cash = float(pf.get("cash", 0) or 0)
    intraday = range_ in _INTRADAY_RANGES
    points_n = _RANGE_POINTS.get(range_, _RANGE_POINTS["6mo"])
    symbols = [h["symbol"] for h in holdings]
    if intraday:
        market_data.warm_intraday(symbols, range_)
    else:
        market_data.warm_cache(symbols)

    per_symbol: dict[str, pd.Series] = {}
    total_cost = 0.0
    any_mock = False
    # For the 1d view, accumulate the account's PRIOR-CLOSE value so we can
    # anchor the intraday line to it (matching the hero's "Today"). The intraday
    # series otherwise starts at the OPEN and misses any overnight gap.
    anchor_prev_value = 0.0
    anchor_label: str | None = None
    want_anchor = range_ == "1d"
    for h in holdings:
        sym = h["symbol"].upper()
        shares = float(h.get("shares", 0) or 0)
        total_cost += shares * float(h.get("cost_basis", 0) or 0)
        live = None
        try:
            if intraday:
                df, source = market_data.get_intraday(sym, range_)
                closes = df["Close"].copy()
                try:
                    dmd = market_data.get_market_data(sym)
                    live = dmd.live_price
                    if want_anchor:
                        pc = _prior_session_close(dmd)
                        if pc is not None:
                            anchor_prev_value += pc[0] * shares
                            anchor_label = anchor_label or pc[1]
                except Exception:
                    live = None
            else:
                md = market_data.get_market_data(sym)
                closes, source = md.history["Close"].copy(), md.source
                live = md.live_price
        except Exception:
            continue
        any_mock = any_mock or source == "mock"
        # Make the FINAL point the SAME price the hero total uses, via the one
        # shared rule. This used to override with md.live_price unconditionally
        # — but the hero stopped trusting that field when it was found to lag a
        # full session, so the override became the cause of the drift instead
        # of the cure: every holding sat a few dollars high and the two numbers
        # on the same screen disagreed by ~$40. .copy() above keeps us from
        # mutating the cached history.
        if not intraday and source != "mock" and len(closes):
            from .technical import current_price
            pair = current_price(md)
            if pair:
                closes.iloc[-1] = pair[0]
        elif intraday and live and source != "mock" and len(closes):
            # Intraday bars are their own ledger; the live tick is the right
            # tail for them.
            closes.iloc[-1] = float(live)
        # Strip the timezone before storing. Live bars come back tz-aware
        # (America/New_York) and mock bars are tz-naive, so one symbol that
        # degrades to mock makes the concat below raise "Cannot join tz-naive
        # with tz-aware DatetimeIndex" and 502s the ENTIRE chart. Normalising
        # here means a bad symbol costs its own line and nothing else.
        if getattr(closes.index, "tz", None) is not None:
            closes = closes.copy()
            closes.index = closes.index.tz_localize(None)
        per_symbol[sym] = closes * shares

    points: list[ValuePoint] = []
    if per_symbol:
        # concat unions the date indexes; column-by-column assignment would
        # silently truncate everything to the first symbol's calendar.
        value_frame = pd.concat(per_symbol, axis=1).sort_index().ffill()
        # Leading bars where a symbol has no data yet would understate the
        # total — drop them instead of zero-filling.
        # Cash is a flat line added to every point so the chart's total (and its
        # final point) matches the account total shown up top.
        series = value_frame.dropna().sum(axis=1) + cash
        if not intraday:
            series = series.tail(points_n)
        fmt = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
        for idx, val in series.items():
            points.append(
                ValuePoint(date=pd.Timestamp(idx).strftime(fmt), value=round(float(val), 2))
            )

    # Anchor the 1d line to the prior-session close (+ cash), so its % is taken
    # vs yesterday's close — the same baseline as the hero's "Today" — and the
    # line visibly starts there and shows any overnight gap, instead of starting
    # at the open and reporting only intraday drift.
    if want_anchor and points and anchor_prev_value:
        points.insert(0, ValuePoint(
            date=anchor_label or points[0].date,
            value=round(anchor_prev_value + cash, 2),
        ))

    return PortfolioHistory(
        range=range_,
        source="mock" if any_mock else "live",
        cost_basis=round(total_cost, 2),
        points=points,
        benchmark=_benchmark_series(points, range_, intraday),
    )


_BENCHMARK = "SPY"


def _benchmark_series(points: list[ValuePoint], range_: str,
                      intraday: bool) -> list[ValuePoint]:
    """The index over the same window, rebased to the portfolio's first value.

    Rebasing rather than plotting SPY's own price is the whole point: on one
    shared axis the two lines start together, so the distance between them at
    any moment IS the out- or under-performance. A raw SPY price line next to a
    $9k account would just be two unrelated squiggles.

    Returns an empty list on any failure — a missing benchmark should quietly
    drop the comparison line, never break the chart.
    """
    if len(points) < 2:
        return []
    try:
        if intraday:
            df, source = market_data.get_intraday(_BENCHMARK, range_)
            closes = df["Close"]
        else:
            md = market_data.get_market_data(_BENCHMARK)
            source = md.source
            closes = md.history["Close"]
        if source != "live" or closes is None or closes.empty:
            return []
        if getattr(closes.index, "tz", None) is not None:
            closes = closes.copy()
            closes.index = closes.index.tz_localize(None)

        fmt = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
        by_label = {pd.Timestamp(i).strftime(fmt): float(v) for i, v in closes.items()}

        start_value = points[0].value
        base = None
        out: list[ValuePoint] = []
        for p in points:
            px = by_label.get(p.date)
            if px is None:
                continue
            if base is None:
                base = px
            out.append(ValuePoint(date=p.date,
                                  value=round(start_value * px / base, 2)))
        # A couple of matched dates is not a comparison worth drawing.
        return out if len(out) >= max(2, len(points) // 4) else []
    except Exception as exc:
        print(f"[portfolio] benchmark series failed: {exc!r}")
        return []
