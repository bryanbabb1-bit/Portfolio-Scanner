"""Pre-ignition squeeze setups — the screen the other one couldn't be.

WHY THE LOW-FLOAT SCREEN ONLY EVER SAYS AVOID
---------------------------------------------
Two of its five filters are `volume today > 4M` and `rvol > 2x`. Neither can be
true until the move has ALREADY started. So the screen structurally surfaces
names mid-pop — today's candidates were +236%, +60%, +40% ON THE DAY — and any
sound judge looking at a 236% one-day spike says don't chase it.

The AVOIDs were right. The screen was asking the wrong question. It is a
detector of runs in progress, not of runs about to happen, and no amount of
re-judging changes that.

WHAT ACTUALLY PRECEDES A SQUEEZE
--------------------------------
A squeeze needs fuel, a constraint, and a spark, and the first two are visible
BEFORE the third:

  FUEL        short interest as a % of float. Shorts are forced buyers; the
              bigger that pile, the more buying is queued up involuntarily.
  CONSTRAINT  a small float. The same forced buying against fewer shares moves
              price further.
  PRESSURE    days-to-cover — short shares over average daily volume. This is
              the number most people miss: 30% short interest that can exit in a
              day is not a squeeze, and 12% that needs a week is.
  COILED      price NOT yet extended. The whole point is to be early, so a name
              already up 50% is disqualified rather than rewarded.
  WARMING     volume modestly elevated, not exploded. Accumulation reads as
              1.2-3x; 40x means you are late.

WHAT THIS CANNOT SEE
--------------------
The two best real-time signals are not in free data: borrow fee and share
availability. When a borrow rate goes from 5% to 300% the squeeze is hours away,
and this screen will not know. Short interest from exchanges is also reported
twice a month with a lag, so a number here can be two weeks stale — long enough
for the position to have already covered.

So this finds CONDITIONS, not timing. It is a watchlist generator.
"""
from __future__ import annotations

import time

from ..config import settings

# Fuel. Below ~10% there is nothing to squeeze; 20%+ is genuinely crowded.
MIN_SHORT_PCT = 12.0
# Constraint. Squeezes happen where supply is scarce.
MAX_FLOAT = 75_000_000
# Pressure. Shorts needing this many days of average volume to get out.
MIN_DAYS_TO_COVER = 2.5
# Coiled, not launched — the filter the other screen is missing entirely.
MAX_CHANGE_TODAY = 12.0
MAX_RUN_20D = 60.0
# Warming, not exploded.
MIN_RVOL = 1.1
MAX_RVOL = 6.0
MIN_PRICE = 1.50
MAX_CAP = 5_000_000_000

PAGE_SIZE = 25
MAX_PAGES = 80
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL = 900


def _score(short_pct, dtc, float_m, rvol) -> float:
    """Rank by how much force is coiled, not by how much has already moved."""
    s = 0.0
    s += min(short_pct, 60) * 1.2          # fuel
    s += min(dtc, 15) * 4.0                # pressure matters most
    s += max(0, (75 - float_m)) * 0.35     # scarcer float, bigger move
    s += min(rvol, 4) * 3.0                # someone is starting to notice
    return round(s, 1)


def screen(force: bool = False, limit: int = 25) -> dict:
    """Names where a squeeze COULD happen, before it does."""
    if settings.DATA_MODE == "mock":
        return {"results": [], "note": "mock data — screen not run"}

    hit = _CACHE.get("squeeze")
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return {"results": hit[1], "cached": True, "filters": describe()}

    rows: dict[str, dict] = {}
    scanned = 0
    total = None
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q

        q = Q("and", [
            Q("gt", ["intradayprice", MIN_PRICE]),
            Q("lt", ["intradaymarketcap", MAX_CAP]),
            Q("gt", ["dayvolume", 200_000]),
        ])
        offset = 0
        for _ in range(MAX_PAGES):
            # Yahoo throttles a fast paging walk and answers with an EMPTY page
            # rather than an error, which silently truncates the scan to one
            # page and reports 0.4% coverage as if it were a finished screen.
            # Pace the walk and retry an empty page once before believing it.
            quotes = []
            for attempt in range(2):
                try:
                    res = yf.screen(q, count=PAGE_SIZE, offset=offset,
                                    sortField="dayvolume", sortAsc=False)
                except Exception as exc:
                    print(f"[squeeze] page {offset} failed: {exc!r}")
                    res = {}
                if total is None:
                    total = res.get("total") if isinstance(res, dict) else None
                quotes = res.get("quotes", []) if isinstance(res, dict) else []
                if quotes:
                    break
                time.sleep(1.5)
            time.sleep(0.35)
            if not quotes:
                break
            scanned += len(quotes)
            before = len(rows)
            for qq in quotes:
                sym = qq.get("symbol")
                if sym and "." not in sym and "-" not in sym:
                    rows.setdefault(sym, qq)
            if len(rows) == before:
                break
            offset += len(quotes)
            if total and offset >= total:
                break
    except Exception as exc:
        return {"results": [], "note": f"screener unavailable: {exc}",
                "filters": describe()}

    from . import market_data

    out: list[dict] = []
    for sym, q in rows.items():
        chg = float(q.get("regularMarketChangePercent") or 0)
        # Reject the already-launched FIRST — it is the cheapest filter and the
        # whole point of this screen.
        if chg > MAX_CHANGE_TODAY:
            continue
        vol = q.get("regularMarketVolume") or 0
        avg = q.get("averageDailyVolume3Month") or 0
        if not vol or not avg:
            continue
        rvol = vol / avg
        if not (MIN_RVOL <= rvol <= MAX_RVOL):
            continue

        try:
            md = market_data.get_market_data(sym)
            st = md.structure or {}
        except Exception:
            continue
        short_pct = st.get("short_pct_float")
        flt = st.get("float_shares")
        if not short_pct or not flt:
            continue
        short_pct *= 100 if short_pct <= 1 else 1     # some feeds give a ratio
        if short_pct < MIN_SHORT_PCT or flt > MAX_FLOAT:
            continue

        # Days to cover: the pressure number most screens omit.
        short_shares = flt * (short_pct / 100.0)
        dtc = short_shares / avg if avg else 0
        if dtc < MIN_DAYS_TO_COVER:
            continue

        # Not already run. A squeeze you are late to is somebody else's.
        run20 = None
        try:
            h = md.history
            if h is not None and len(h) > 21:
                run20 = (float(h["Close"].iloc[-1]) / float(h["Close"].iloc[-21]) - 1) * 100
                if run20 > MAX_RUN_20D:
                    continue
        except Exception:
            pass

        out.append({
            "symbol": sym,
            "name": q.get("shortName") or sym,
            "price": round(float(q.get("regularMarketPrice") or 0), 2),
            "change_pct": round(chg, 2),
            "short_pct_float": round(short_pct, 1),
            "float_shares": int(flt),
            "days_to_cover": round(dtc, 1),
            "rvol": round(rvol, 2),
            "run_20d_pct": round(run20, 1) if run20 is not None else None,
            "coil_score": _score(short_pct, dtc, flt / 1e6, rvol),
        })

    out.sort(key=lambda r: -r["coil_score"])
    out = out[:limit]
    _CACHE["squeeze"] = (time.time(), out)
    return {"results": out, "scanned": scanned, "universe_total": total,
            "coverage_pct": round(scanned / total * 100, 1) if total else None,
            "cached": False, "filters": describe()}


def describe() -> dict:
    return {
        "min_short_pct_float": MIN_SHORT_PCT,
        "max_float": MAX_FLOAT,
        "min_days_to_cover": MIN_DAYS_TO_COVER,
        "max_change_today_pct": MAX_CHANGE_TODAY,
        "max_run_20d_pct": MAX_RUN_20D,
        "rvol_band": [MIN_RVOL, MAX_RVOL],
        "why": ("The low-float screen requires 4M shares and 2x rvol, which "
                "cannot be true until the move has already started — so it "
                "finds runs in progress and the desk correctly says don't "
                "chase. This finds the conditions BEFORE the spark."),
        "blind_spots": ("Borrow fee and share availability are the two best "
                        "real-time squeeze signals and are not in free data. "
                        "Exchange short interest is reported twice monthly with "
                        "a lag, so a figure here can be two weeks stale. This "
                        "finds conditions, not timing."),
    }
