"""Beaten down, and starting to turn — the setup you cannot wait for news on.

THE PROBLEM WITH THE OTHER SCREENS
----------------------------------
The low-float screen requires 4M shares and 2x volume TODAY, so it only fires
once a name is already running, and the desk correctly refuses to chase a 236%
one-day spike. A screen that can only find ignition will only ever produce
AVOID. That is not the judge being negative; it is the screen handing it
unanswerable questions.

By the time the news is out and the volume is obvious, the move is priced. The
setup worth finding is the one BEFORE that: a name that has already been
destroyed, has stopped going down, and has just begun to turn.

WHY THIS ONE AND NOT ANOTHER MOMENTUM SCREEN
--------------------------------------------
This is the only setup family this codebase has ever measured an edge in. The
learning loop's five-year replay found every BUY rule profitable and every SELL
rule losing, with oversold-at-support at a 2.69 profit factor. The swing model
built on the same idea — buy weakness inside strength — measured +0.233R with a
t-statistic of 2.48, the only strategy here that ever cleared significance.

So this is not a new guess. It is the one thing that has already worked, pointed
at beaten-down names instead of uptrends.

WHAT A TURN LOOKS LIKE BEFORE THE NEWS
--------------------------------------
  DESTROYED      well off the 52-week high. Without this it is just momentum.
  STOPPED FALLING  the recent low is holding — a higher low, not a new one.
  RECLAIM        back above the 20-day after being below it. The first
                 objective evidence that sellers lost control.
  PARTICIPATION  the reclaim happens on above-average volume. A drift back over
                 a moving average on no volume is noise.
  EARLY          not already up hugely. If it has run 60% you are the exit
                 liquidity, not the entry.
  ALIVE          real liquidity and a real price. A $0.30 shell bouncing is not
                 a recovery, it is a dead cat with a reverse split coming.
"""
from __future__ import annotations

import time

from ..config import settings

MIN_DRAWDOWN_PCT = 30.0     # how far below the 52w high to count as beaten down
MAX_DRAWDOWN_PCT = 92.0     # past this it is usually terminal, not cheap
MAX_RUN_20D = 45.0          # still early
RECLAIM_LOOKBACK = 10       # sessions to prove it WAS below the 20-day
MIN_DAYS_BELOW = 3          # ...and genuinely below, not clipped once on noise
MIN_CROSS_MARGIN = 0.015    # the cross must mean something, not 0.1%
MIN_RVOL = 1.15             # someone showed up for the reclaim
MIN_PRICE = 2.00
MIN_AVG_VOL = 300_000
MAX_CAP = 20_000_000_000

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL = 900


def analyse(hist, rvol: float | None) -> dict | None:
    """Score one name's history for a reclaim. None when it isn't one."""
    import pandas as pd

    if hist is None or len(hist) < 60:
        return None
    close = hist["Close"]
    price = float(close.iloc[-1])
    high52 = float(close.tail(252).max())
    if high52 <= 0:
        return None
    drawdown = (1 - price / high52) * 100
    if not (MIN_DRAWDOWN_PCT <= drawdown <= MAX_DRAWDOWN_PCT):
        return None

    sma20 = close.rolling(20).mean()
    if pd.isna(sma20.iloc[-1]):
        return None
    # Above the 20-day NOW, and genuinely below it inside the lookback.
    #
    # "Below it at least once" is not enough: a name drifting sideways ABOVE its
    # 20-day clips it on noise every few sessions and scored as a reclaim. In
    # testing a stale drifter scored 95.9 against 75.1 for a real turn — exactly
    # backwards. A reclaim needs a sustained period below, and a cross with some
    # conviction behind it rather than a rounding error.
    sma_now = float(sma20.iloc[-1])
    if price <= sma_now * (1 + MIN_CROSS_MARGIN):
        return None
    window = close.iloc[-RECLAIM_LOOKBACK:] <= sma20.iloc[-RECLAIM_LOOKBACK:]
    days_below = int(window.sum())
    if days_below < MIN_DAYS_BELOW:
        return None

    # A higher low: the recent trough is above the trough before it. This is
    # what separates "stopped falling" from "still falling, briefly bouncing".
    recent_low = float(close.iloc[-20:].min())
    prior_low = float(close.iloc[-60:-20].min())
    higher_low = recent_low > prior_low

    run20 = (price / float(close.iloc[-21]) - 1) * 100 if len(close) > 21 else 0.0
    if run20 > MAX_RUN_20D:
        return None

    off_low = (price / recent_low - 1) * 100 if recent_low else 0.0
    score = 0.0
    score += min(drawdown, 90) * 0.6            # more damage, more to recover
    score += 25 if higher_low else 0            # the structural tell
    score += max(0, 25 - days_below) * 0.8      # a FRESH reclaim, not an old one
    score += min((rvol or 1) * 8, 30)           # participation
    score -= max(0, off_low - 25) * 0.5         # already bounced = later entry
    return {
        "drawdown_pct": round(drawdown, 1),
        "run_20d_pct": round(run20, 1),
        "off_recent_low_pct": round(off_low, 1),
        "higher_low": higher_low,
        "days_below_20d": days_below,
        "reclaim_score": round(score, 1),
    }


BATCH = 250          # symbols per bulk download request


def _batch_history(symbols: list[str]):
    """One year of daily closes+volume for many symbols, in bulk.

    yfinance downloads a batch in a single request, so 5,900 names cost ~24
    requests instead of 5,900. That is the difference between a screen that can
    see the market and one that pages through a keyhole.
    """
    import pandas as pd
    import yfinance as yf

    frames = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i:i + BATCH]
        try:
            df = yf.download(chunk, period="1y", interval="1d",
                             auto_adjust=True, progress=False, threads=True,
                             group_by="ticker")
        except Exception as exc:
            print(f"[reclaim] batch {i}: {exc!r}")
            continue
        for sym in chunk:
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub.dropna(subset=["Close"])
                if len(sub) >= 60:
                    frames[sym] = sub
            except Exception:
                continue
        print(f"[reclaim] {min(i + BATCH, len(symbols))}/{len(symbols)} "
              f"({len(frames)} usable)")
    return frames


def screen(force: bool = False, limit: int = 25,
           max_symbols: int | None = None) -> dict:
    """Scan the WHOLE US listed market for reclaim setups."""
    if settings.DATA_MODE == "mock":
        return {"results": [], "note": "mock data — screen not run"}
    hit = _CACHE.get("reclaim")
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return {"results": hit[1], "cached": True, "filters": describe()}

    from . import universe

    symbols = universe.all_symbols()
    if max_symbols:
        symbols = symbols[:max_symbols]
    if not symbols:
        return {"results": [], "note": "universe unavailable",
                "filters": describe()}

    frames = _batch_history(symbols)

    out: list[dict] = []
    for sym, h in frames.items():
        try:
            close = h["Close"]
            price = float(close.iloc[-1])
            if price < MIN_PRICE:
                continue
            vol = h["Volume"]
            avg = float(vol.tail(60).mean())
            if not avg or avg < MIN_AVG_VOL:
                continue
            rvol = float(vol.iloc[-1]) / avg if avg else 0
            if rvol < MIN_RVOL:
                continue
            a = analyse(h, rvol)
            if not a:
                continue
            prev = float(close.iloc[-2]) if len(close) > 1 else price
            out.append({
                "symbol": sym,
                "price": round(price, 2),
                "change_pct": round((price / prev - 1) * 100, 2) if prev else 0.0,
                "avg_volume": int(avg),
                "rvol": round(rvol, 2),
                **a,
            })
        except Exception:
            continue

    out.sort(key=lambda r: -r["reclaim_score"])
    out = out[:limit]
    _CACHE["reclaim"] = (time.time(), out)
    return {"results": out, "scanned": len(frames),
            "universe_total": len(symbols),
            "coverage_pct": round(len(frames) / len(symbols) * 100, 1)
            if symbols else None,
            "cached": False, "filters": describe()}


def describe() -> dict:
    return {
        "min_drawdown_pct": MIN_DRAWDOWN_PCT,
        "max_drawdown_pct": MAX_DRAWDOWN_PCT,
        "reclaim_lookback_days": RECLAIM_LOOKBACK,
        "max_run_20d_pct": MAX_RUN_20D,
        "min_rvol": MIN_RVOL,
        "thesis": ("Beaten down, stopped falling, and just reclaimed the 20-day "
                   "on real volume. Detectable BEFORE the news — by the time a "
                   "catalyst is public the move is priced."),
        "why_trusted": ("The only setup family this codebase has measured an "
                        "edge in: oversold-at-support at 2.69 profit factor over "
                        "five years, and the swing model on the same idea at "
                        "+0.233R with t=2.48."),
        "not_a_squeeze_screen": ("This deliberately does NOT require a volume "
                                 "explosion. A screen that needs ignition can "
                                 "only ever find names already running, which is "
                                 "why the low-float screen returns nothing but "
                                 "AVOID."),
    }
