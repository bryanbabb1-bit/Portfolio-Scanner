"""Pullback in an uptrend — the one edge in this codebase that survived a
five-year replay with a t-statistic above 2.

THE RULE, AND WHY IT IS THIS ONE
--------------------------------
It was not guessed. The learning loop's own replay graded every rule in the
app and found oversold-at-support at a 2.69 profit factor while every sell
rule lost money. The swing study (`151ff08`) modelled that finding directly
over 149 trades and 5 years: win 55.7%, PF 1.65, expectancy +0.233R,
**t = 2.48**, bootstrap CI +0.050..+0.424R.

    buy weakness inside strength, never weakness on its own

Three conditions, and the order is the argument:

  1. price above the 200-day  — the regime filter does the heavy lifting.
     Buying an oversold stock is a good idea in an uptrend and a catastrophe
     in a downtrend, and the 200-day is the difference between the two.
  2. RSI was below 35 on the previous bar — a real pullback, not a wobble.
  3. RSI is HIGHER than it was — the turn has started. A test asserts a
     falling knife is not caught.

WHY IT LIVES IN THE SLEEVE
--------------------------
The same study found this edge LOSES to buy-and-hold at 2% risk across four
slots (10.82% vs SPY 13.37%) and BEATS it concentrated (1 slot at 8%: 19.13%
vs 15.25% over 15 years, in both halves of an out-of-sample split). The edge
was never the problem; the sizing was. The sleeve runs it at 5% across two
slots — inside that range, and forward-tested rather than assumed, because
1-slot/8% was the best of about twelve configurations tried and that makes it
weaker evidence than a pre-registered test.

Daily bars, so this scans ONCE a session. It costs no CLI calls.
"""
from __future__ import annotations

import time

from ..config import settings
from .technical import compute_indicators

# Liquid names with multi-year history, spread across sectors so a result is
# not one sector's story — the universe the 5-year replay actually used, plus
# whatever the book holds or watches. Survivorship is a known bias (these are
# companies still liquid today) and is a caveat on the backtest, not a defect
# in the live screen, which only ever sees today.
UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "XLE", "XLF", "XLV", "XLI",
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "GOOGL", "META", "AMZN",
    "JPM", "BAC", "V", "MA", "UNH", "JNJ", "LLY", "MRK", "PFE",
    "CAT", "HON", "GE", "WMT", "COST", "HD", "MCD", "NKE",
    "XOM", "CVX", "COP", "NEE", "DUK", "CRM", "ADBE", "NFLX",
    "VST", "CEG", "ETN", "PWR", "GEV", "ANET", "CRWD", "NET", "PLTR", "MU",
)

RSI_ENTRY = 35.0        # oversold ENOUGH to be a real pullback
_CACHE: dict[str, tuple[float, list[dict]]] = {}
TTL = 3600              # daily bars; hourly is already more often than it changes


def _preferences_block() -> set[str]:
    """Names Bryan has told the desk to stop recommending. A screen that
    ignores a standing instruction is the bug this app already fixed once."""
    try:
        from . import preferences
        return preferences.blocked_symbols()
    except Exception:
        return set()


def _universe() -> list[str]:
    syms: list[str] = []
    seen: set[str] = set()

    def push(sym: str) -> None:
        s = (sym or "").upper().strip()
        if s and s not in seen:
            seen.add(s)
            syms.append(s)

    try:
        from . import portfolio as pf_service
        book = pf_service.load_portfolio()
        for h in book.get("holdings", []):
            push(h.get("symbol", ""))
        for w in book.get("watchlist", []):
            push(w.get("symbol", ""))
    except Exception:
        pass
    for s in UNIVERSE:
        push(s)
    blocked = _preferences_block()
    return [s for s in syms if s not in blocked]


def evaluate(symbol: str, md, cfg: dict) -> dict | None:
    """One name against the rule. None when it is not a setup.

    Returns the ticket levels rather than an opinion: entry at the last price,
    stop 2.5 ATR below (the replay's distance), and the facts that justify it.
    """
    if md is None or md.history is None or md.history.empty:
        return None
    if md.source != "live":
        return None          # never screen on fallback data
    ind = compute_indicators(md.history)
    price = float(md.history["Close"].iloc[-1])
    if not price or price <= 0:
        return None
    sma200, rsi, rsi_prev, atr = ind.sma200, ind.rsi, ind.rsi_prev, ind.atr
    if None in (sma200, rsi, rsi_prev, atr) or atr <= 0:
        return None
    if price <= sma200:
        return None                       # not an uptrend; not our trade
    if rsi_prev >= RSI_ENTRY:
        return None                       # was not oversold going in
    if rsi <= rsi_prev:
        return None                       # still falling — do not catch it
    stop = price - float(cfg["pullback_atr_stop"]) * atr
    if stop <= 0 or stop >= price:
        return None
    above = (price / sma200 - 1) * 100
    return {
        "symbol": symbol.upper(),
        "price": round(price, 4),
        "entry": round(price, 4),
        "stop": round(stop, 4),
        "rsi": round(rsi, 1),
        "rsi_prev": round(rsi_prev, 1),
        "atr": round(atr, 4),
        "pct_above_200d": round(above, 1),
        "why": [
            f"Above its 200-day by {above:.0f}% — the regime filter that "
            f"separates a dip from a fall",
            f"RSI turned up {rsi_prev:.0f} to {rsi:.0f} — oversold, and the "
            f"turn has started",
            f"Stop {cfg['pullback_atr_stop']:g} ATR below at "
            f"{stop:.2f} ({(stop / price - 1) * 100:.0f}%)",
        ],
    }


def scan(force: bool = False, cfg: dict | None = None) -> list[dict]:
    """Today's pullback setups across the universe, best first.

    Ranked by how deep the pullback was — a turn from RSI 22 is a bigger
    stretch of the rubber band than one from 34, and the replay's winners
    clustered at the deeper end."""
    if settings.DATA_MODE == "mock":
        return []
    hit = _CACHE.get("scan")
    if hit and not force and (time.time() - hit[0]) < TTL:
        return hit[1]

    from . import market_data, sleeve
    cfg = cfg or sleeve.config()
    syms = _universe()
    try:
        market_data.warm_cache(syms, max_workers=10, light=True)
    except Exception as exc:
        print(f"[pullback] warm failed: {exc!r}")

    out: list[dict] = []
    for sym in syms:
        try:
            hit_row = evaluate(sym, market_data.get_price_data(sym), cfg)
        except Exception as exc:
            print(f"[pullback] {sym}: {exc!r}")
            continue
        if hit_row:
            out.append(hit_row)
    out.sort(key=lambda r: r["rsi_prev"])
    _CACHE["scan"] = (time.time(), out)
    if out:
        print(f"[pullback] {len(out)} setups: {[r['symbol'] for r in out[:6]]}")
    return out
