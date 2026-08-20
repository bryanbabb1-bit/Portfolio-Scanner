"""Where the volume showed up BEFORE the move. The earliest honest signal here.

WHY THE 8-K FEED WAS REPLACED
-----------------------------
The filings feed was complete, structured, official — and lagging. An 8-K is
filed alongside the press release, which means by the time it exists the move
has happened. Its own docstring admitted as much and it shipped anyway. Bryan's
verdict was correct: for someone trying to get in early it is noise.

So instead of asking "what has been announced", this asks "where is something
being accumulated". That question has a measurable answer.

WHAT THE DATA SAYS
------------------
Taking the 195 measured +50% days and looking at the twenty sessions BEFORE each
one, against 5,000 ordinary stock-days:

                        before a +50% day     ordinary day
    5-day volume ratio        1.18 median          0.89
    ...at the 90th pct       33.4x                 1.68x
    20-day drift            -25.0% median         +0.2%

Big moves do not arrive from nowhere. Volume shows up first, and the names it
shows up in are typically already beaten down — which is the reclaim thesis
arriving from a completely different direction.

Forward-tested on 101,240 tradeable stock-days, screening after the close and
entering at the next open:

    filter                    alerts/day   touched +50% in 5d   median 5d
    none (baseline)                3,705          1.3%             0.0%
    prior-day volume >= 3x            94          5.2%            -1.0%
    prior-day volume >= 5x            38          9.6%            -2.7%
    prior-day volume >= 8x            19         13.7%            -8.1%
    prior-day volume >= 12x           12         15.9%           -13.9%

READ BOTH COLUMNS. The screen concentrates big movers more than tenfold — 1.3%
of ordinary days touch +50% in a week, 13.7% of these do. It also has a median
outcome of MINUS eight per cent, and the tighter the filter the worse that
number gets. Both tails fatten; the left one is heavier.

That makes this a hunting ground, not a buy list, and the panel says so. Buying
everything it flags loses money exactly as chasing runners did. Its value is
that roughly two and a half names a day which are ABOUT to move are somewhere
in a list of nineteen, a day before the move — and picking among them needs a
reason (a catalyst, a partner trial, a thesis), which is what the rest of this
app is for.
"""
from __future__ import annotations

import json
import time

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "accumulation.json"
TTL = 6 * 3600            # the inputs are daily bars; nothing moves faster
BATCH = 250

# The measured knee. 8x gives ~19 names a day at a 10.5x concentration of big
# movers; 12x buys 2 more points of hit rate for a much worse median.
MIN_VOL_RATIO = 5.0        # surfaced from here up...
ALERT_VOL_RATIO = 8.0      # ...and flagged hard from here
MIN_PRICE = 2.00
MIN_DOLLAR_VOL = 1_000_000
BASE_WINDOW = 60           # sessions of "normal" to measure against
LIMIT = 40


def _read() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _write(d: dict) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[accumulation] persist failed: {exc!r}")


def analyse(hist) -> dict | None:
    """One name's volume footprint. None when there is nothing unusual."""
    if hist is None or len(hist) < BASE_WINDOW + 25:
        return None
    close, vol = hist["Close"], hist["Volume"]
    price = float(close.iloc[-1])
    if price < MIN_PRICE:
        return None

    # The baseline deliberately EXCLUDES the last week. Including the surge in
    # its own average is how a name that has been loud for days looks normal.
    base = float(vol.iloc[-(BASE_WINDOW + 5):-5].mean())
    if not base or base * price < MIN_DOLLAR_VOL:
        return None

    last = float(vol.iloc[-1])
    week = float(vol.iloc[-5:].mean())
    ratio = last / base
    if ratio < MIN_VOL_RATIO:
        return None

    drift20 = ((price / float(close.iloc[-21]) - 1) * 100
               if len(close) > 21 else 0.0)
    day = ((price / float(close.iloc[-2]) - 1) * 100
           if len(close) > 1 else 0.0)
    return {
        "price": round(price, 2),
        "vol_ratio": round(ratio, 1),
        "week_ratio": round(week / base, 1),
        "avg_dollar_vol": int(base * price),
        "drift_20d": round(drift20, 1),
        "change_pct": round(day, 2),
        # Beaten down AND suddenly busy is the profile the study found: the
        # median name that ran 50% was down 25% on the month beforehand.
        "beaten_down": drift20 < -10,
        "loud": ratio >= ALERT_VOL_RATIO,
    }


def _batch_history(symbols: list[str]):
    import pandas as pd
    import yfinance as yf

    frames = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i:i + BATCH]
        try:
            df = yf.download(chunk, period="6mo", interval="1d",
                             auto_adjust=False, progress=False, threads=True,
                             group_by="ticker")
        except Exception as exc:
            print(f"[accumulation] batch {i}: {exc!r}")
            continue
        for sym in chunk:
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub.dropna(subset=["Close", "Volume"])
                if len(sub) >= BASE_WINDOW + 25:
                    frames[sym] = sub
            except Exception:
                continue
    return frames


def build(symbols: list[str] | None = None, limit: int = LIMIT) -> dict:
    if settings.DATA_MODE == "mock":
        return {"ts": time.time(), "results": [], "note": "mock data"}

    from . import universe

    syms = symbols if symbols is not None else universe.all_symbols()
    frames = _batch_history(syms)

    out = []
    for sym, h in frames.items():
        try:
            a = analyse(h)
        except Exception:
            continue
        if a:
            out.append({"symbol": sym, **a})

    out.sort(key=lambda r: -r["vol_ratio"])
    out = out[:limit]
    return {
        "ts": time.time(),
        "scanned": len(frames),
        "universe": len(syms),
        "results": out,
        "thresholds": {"surface": MIN_VOL_RATIO, "loud": ALERT_VOL_RATIO},
        "measured": {
            "baseline_touch_50": 1.3,
            "at_8x_touch_50": 13.7,
            "at_8x_median_5d": -8.1,
            "alerts_per_day_at_8x": 19,
        },
    }


def get(force: bool = False) -> dict:
    cached = _read()
    if not force and cached and time.time() - float(cached.get("ts", 0)) < TTL:
        return {**cached, "cached": True}
    out = build()
    _write(out)
    return {**out, "cached": False}
