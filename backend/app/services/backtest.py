"""Backtest — replay the live conviction rules over real price history.

The point is validation, not curve-fitting: every rule that can fire a slap at
the client should have to show what it did the last thousand times conditions
looked like this.

THE CRITICAL DESIGN CONSTRAINT is that this must not become a SECOND copy of
the rules. A backtest that drifts from production is worse than no backtest —
it certifies behaviour the app doesn't have. So this calls `conviction._detect`
itself, unchanged, once per historical bar. The only new code is
`technical.indicator_frame`, which produces the same indicators as
`compute_indicators` for every bar instead of just the last one; each row is
shimmed into the shape `_detect` already expects.

`screener.breakout_score` is a pure function of indicators and price with no
analyst inputs, so the score used at each historical bar is genuinely the
score that bar would have produced — no lookahead.

What this deliberately does NOT model: slippage, commissions, position sizing,
or the advisor's veto (`conviction._enrich` can overrule a screen, and does).
It also runs over the CURRENT universe, which is survivorship-biased by
construction. Every one of those makes results flattering. The UI says so.
"""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ..config import settings
from . import conviction, market_data, screener, technical
from . import portfolio as pf_service

_FILE = settings.PORTFOLIO_FILE.parent / "backtest.json"
_store_lock = threading.Lock()

# Forward horizons, in trading days, at which each signal is graded.
HORIZONS = (5, 20, 60)
GRADE_AT = 20            # the horizon the headline win rate uses
WARMUP = 200             # bars needed before sma200 is real
HOLD_DAYS = 20           # equity-curve policy: hold each buy this long
BENCHMARK = "SPY"

_IND_FIELDS = (
    "rsi", "rsi_prev", "rsi_min_10d", "ret_5d_pct", "ret_20d_pct",
    "macd", "macd_signal", "macd_hist", "sma20", "sma50", "sma200",
    "ema20", "atr", "bb_upper", "bb_lower", "high_52w", "low_52w",
    "pct_from_52w_high", "avg_volume_20", "volume_ratio", "trend",
)


def _clean(v):
    """NaN -> None, so the shim behaves like the pydantic model (Optional)."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(f) or np.isinf(f)) else f


def _row_shim(row) -> tuple[SimpleNamespace, SimpleNamespace]:
    """Turn one indicator-frame row into the (ind, quote) pair `_detect` wants."""
    ind = SimpleNamespace(**{f: _clean(row.get(f)) for f in _IND_FIELDS})
    quote = SimpleNamespace(
        price=_clean(row.get("price")),
        change_pct=_clean(row.get("change_pct")) or 0.0,
        # `_detect` refuses to fire on source="mock" so a failed LIVE fetch can
        # never produce a real slap off a stale price. That guard is about live
        # quotes; here we are feeding genuine historical bars, so it must not
        # suppress the replay.
        source="live",
        name=None,
    )
    return ind, quote


def replay_symbol(
    symbol: str,
    held: bool = True,
    years: int = 5,
) -> list[dict]:
    """Every signal the live rules would have fired on `symbol`, graded forward."""
    try:
        md = market_data.get_deep_history(symbol, years=years)
    except Exception:
        return []

    df = md.history
    if df is None or len(df) < WARMUP + max(HORIZONS) + 5:
        return []
    df = df.tail(years * 252 + WARMUP)

    frame = technical.indicator_frame(df)
    close = df["Close"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in df.index]
    n = len(close)

    records = frame.to_dict("records")
    out: list[dict] = []

    for i in range(WARMUP, n - max(HORIZONS)):
        row = records[i]
        if row.get("sma200") is None or (isinstance(row.get("sma200"), float)
                                         and np.isnan(row["sma200"])):
            continue
        ind, quote = _row_shim(row)
        if quote.price is None:
            continue

        score = screener.breakout_score(ind, quote)
        # THE live rule engine, unchanged. pl_pct is None: unrealized P/L is a
        # property of the client's cost basis, not of history, and no rule in
        # `_detect` reads it.
        try:
            sigs = conviction._detect(symbol, ind, quote, held, None, score)
        except Exception:
            continue
        if not sigs:
            continue

        entry = close[i]
        if not entry or entry <= 0:
            continue

        for s in sigs:
            rec = {
                "symbol": symbol,
                "date": dates[i],
                "rule": s["rule"],
                "side": s["side"],
                "price": round(entry, 2),
                "score": round(score, 1),
                "bar": i,
            }
            for h in HORIZONS:
                fwd = (close[i + h] / entry - 1) * 100
                # A SELL "wins" when the price falls — same sign convention as
                # the live scorecard, so backtest and live numbers compare.
                rec[f"fwd_{h}"] = round(float(fwd), 2)
                rec[f"eff_{h}"] = round(float(fwd if s["side"] == "buy" else -fwd), 2)
            # Worst drawdown while the trade was open — how much pain it took
            # to earn the result. Average return alone hides unholdable trades.
            window_low = float(np.min(low[i + 1 : i + 1 + GRADE_AT]))
            rec["mae_pct"] = round((window_low / entry - 1) * 100, 2)
            out.append(rec)

    return out


def _rule_stats(sigs: list[dict]) -> list[dict]:
    by_rule: dict[str, list[dict]] = {}
    for s in sigs:
        by_rule.setdefault(s["rule"], []).append(s)

    stats = []
    for rule, rows in by_rule.items():
        effs = [r[f"eff_{GRADE_AT}"] for r in rows]
        wins = [e for e in effs if e > 0]
        losses = [e for e in effs if e <= 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        stats.append({
            "rule": rule,
            "side": rows[0]["side"],
            "signals": len(rows),
            "win_rate": round(100 * len(wins) / len(effs), 1),
            "avg_5": round(sum(r["eff_5"] for r in rows) / len(rows), 2),
            "avg_20": round(sum(effs) / len(effs), 2),
            "avg_60": round(sum(r["eff_60"] for r in rows) / len(rows), 2),
            "best": round(max(effs), 2),
            "worst": round(min(effs), 2),
            # A profit factor below 1 means the rule loses money at this horizon.
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
            "avg_mae": round(sum(r["mae_pct"] for r in rows) / len(rows), 2),
            "symbols": len({r["symbol"] for r in rows}),
        })
    stats.sort(key=lambda s: -s["avg_20"])
    return stats


def _equity_curve(buys: list[dict], years: int) -> dict:
    """Equal-weight-of-open-positions curve vs SPY buy-and-hold.

    Policy, stated plainly because it is an assumption and not a fact: every
    BUY signal opens an equal-weight position the NEXT bar and holds it for
    HOLD_DAYS. On any given day the strategy's return is the mean daily return
    of whatever is open; with nothing open it is flat (in cash). No slippage,
    no commissions, no compounding into position size.
    """
    closes: dict[str, pd.Series] = {}
    for sym in set([b["symbol"] for b in buys] + [BENCHMARK]):
        try:
            md = market_data.get_deep_history(sym, years=years)
        except Exception:
            continue
        c = md.history["Close"].copy()
        idx = pd.to_datetime(c.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        c.index = idx.normalize()
        closes[sym] = c[~c.index.duplicated(keep="last")]

    if BENCHMARK not in closes or not buys:
        return {"points": [], "note": "Not enough signals to build a curve."}

    bench = closes[BENCHMARK].tail(years * 252)
    cal = bench.index
    rets = {s: c.pct_change().reindex(cal) for s, c in closes.items()}

    # Mark which days each position is open.
    open_ret = pd.DataFrame(0.0, index=cal, columns=["sum"])
    open_cnt = pd.Series(0, index=cal)
    for b in buys:
        r = rets.get(b["symbol"])
        if r is None:
            continue
        try:
            start = cal.get_indexer([pd.Timestamp(b["date"])], method="bfill")[0]
        except Exception:
            continue
        if start < 0:
            continue
        lo, hi = start + 1, min(start + 1 + HOLD_DAYS, len(cal))
        if lo >= hi:
            continue
        seg = r.iloc[lo:hi].fillna(0.0)
        open_ret.iloc[lo:hi, 0] += seg.to_numpy()
        open_cnt.iloc[lo:hi] += 1

    daily = (open_ret["sum"] / open_cnt.replace(0, np.nan)).fillna(0.0)
    strat = (1 + daily).cumprod()
    bh = (1 + rets[BENCHMARK].fillna(0.0)).cumprod()

    points = [
        {"date": d.strftime("%Y-%m-%d"),
         "strategy": round(float(s), 4),
         "benchmark": round(float(b), 4)}
        for d, s, b in zip(cal, strat, bh)
    ]
    # Thin to ~260 points so the payload stays small on the phone.
    step = max(1, len(points) // 260)
    thinned = points[::step]
    if thinned and thinned[-1] is not points[-1]:
        thinned.append(points[-1])

    dd = strat / strat.cummax() - 1
    return {
        "points": thinned,
        "strategy_return_pct": round((float(strat.iloc[-1]) - 1) * 100, 1),
        "benchmark_return_pct": round((float(bh.iloc[-1]) - 1) * 100, 1),
        "max_drawdown_pct": round(float(dd.min()) * 100, 1),
        "days_invested_pct": round(float((open_cnt > 0).mean()) * 100, 0),
        "note": (
            f"Every BUY opens an equal-weight position the next bar and holds "
            f"{HOLD_DAYS} trading days. No slippage, commissions or sizing."
        ),
    }


def last_result() -> dict | None:
    """The most recent completed run, so the page has something on load.

    A replay is CPU-bound over the whole universe; it should be triggered
    deliberately, not recomputed every time someone opens the sheet."""
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _persist(result: dict) -> None:
    try:
        with _store_lock:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[backtest] persist failed: {exc!r}")


def run(years: int = 5, limit: int | None = None) -> dict:
    """Replay every rule across the book + watchlist. CPU-bound; run as a job."""
    started = time.time()
    pf = pf_service.load_portfolio()
    held = {h["symbol"].upper() for h in pf.get("holdings", [])}
    watch = {w["symbol"].upper() for w in pf.get("watchlist", [])}
    universe = sorted(held | watch)
    if limit:
        universe = universe[:limit]

    try:
        market_data.warm_cache(universe + [BENCHMARK], light=True)
    except Exception:
        pass

    all_sigs: list[dict] = []
    skipped: list[str] = []
    for sym in universe:
        sigs = replay_symbol(sym, held=sym in held, years=years)
        if not sigs:
            skipped.append(sym)
        all_sigs.extend(sigs)

    rules = _rule_stats(all_sigs)
    buys = [s for s in all_sigs if s["side"] == "buy"]
    curve = _equity_curve(buys, years)

    effs = [s[f"eff_{GRADE_AT}"] for s in all_sigs]
    wins = [e for e in effs if e > 0]
    losses = [e for e in effs if e <= 0]
    gross_loss = abs(sum(losses))

    dates = sorted(s["date"] for s in all_sigs)
    result = {
        "ts": time.time(),
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "years": years,
        "universe": len(universe),
        "symbols_tested": len(universe) - len(skipped),
        "skipped": skipped,
        "period": {"start": dates[0], "end": dates[-1]} if dates else None,
        "signals": len(all_sigs),
        "win_rate": round(100 * len(wins) / len(effs), 1) if effs else None,
        "avg_return_pct": round(sum(effs) / len(effs), 2) if effs else None,
        "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss else None,
        "max_drawdown_pct": curve.get("max_drawdown_pct"),
        "grade_horizon_days": GRADE_AT,
        "rules": rules,
        "curve": curve,
        "caveats": [
            "Long-only replay of the screen. No slippage, commissions or taxes.",
            "The universe is the CURRENT book and watchlist, which is "
            "survivorship-biased: names already sold or never bought are absent.",
            "The live advisor can overrule a screen before it reaches you; "
            "this replays the screen alone, so it is not the app's net record.",
            f"A SELL is scored as a win when price FALLS over the next "
            f"{GRADE_AT} sessions, matching the live scorecard convention.",
        ],
    }
    # Only a FULL run becomes the saved record. A `limit`ed run is a debugging
    # path over part of the universe; letting it overwrite the real result
    # would silently replace a complete report with a partial one.
    if limit is None:
        _persist(result)
    return result
