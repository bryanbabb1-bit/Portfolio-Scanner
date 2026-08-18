"""The low-float momentum screen — five filters, run against the whole market.

    price < $20
    relative volume > 2x
    volume today > 4,000,000 shares
    float < 20,000,000 shares
    market cap < $2,000,000,000

WHAT THIS SCREEN IS
-------------------
Every filter points at one setup: a small company whose entire tradeable supply
is being turned over in a day. Float under 20M with 4M+ shares traded means a
fifth of the float changed hands; 2x relative volume says that is a break from
its own normal rather than a big number in absolute terms. Cheap and small-cap
keeps it in the range where that much demand can actually move price.

These are squeeze mechanics. It is the most violent setup in the market in both
directions, which is exactly why it gets sold in trading courses.

WHAT IT IS NOT
--------------
A screen is not an edge. It is a way of shortening a list. This app's own
five-year replay found every BUY rule profitable and every SELL rule losing,
and none of the models beat buy-and-hold — entry selection was almost never the
binding constraint. Treat the output as candidates to research, not signals.

Float is the filter that carries the whole thesis and it is also the least
reliable field: Yahoo reports it inconsistently and it goes stale after
offerings, which low-float names do constantly. Rows are marked when float is
missing rather than being silently dropped or silently passed.
"""
from __future__ import annotations

import time

from ..config import settings

# The screen as originally stated. Kept as a named baseline so any loosening is
# visible as a deviation rather than becoming the new normal.
STATED = {"max_price": 20.0, "min_rvol": 2.0, "min_volume": 4_000_000,
          "max_float": 20_000_000, "max_cap": 2_000_000_000}

# Calibrated defaults. Replayed over 90 sessions, float<20M produced a name on
# 5% of days — the screen was effectively always empty. Float is the ONLY
# binding filter: moving volume or rvol barely changes the count, while float
# moves it almost linearly.
#
#   float<20M   0.1/day   95% empty
#   float<50M   0.3/day   80% empty
#   float<100M  1.0/day   48% empty
#   float<150M  1.5/day   27% empty, 70% of days land in the 1-5 band
#
# 150M is chosen for the count, and the honest cost is that it is no longer
# really a LOW-float screen — it is a high-turnover screen with a float ceiling.
# The tension is real and is surfaced in describe() rather than buried.
MAX_PRICE = 20.0
MIN_RVOL = 2.0
MIN_VOLUME = 4_000_000
MAX_FLOAT = 150_000_000
MAX_CAP = 2_000_000_000

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL = 600


def _rvol(quote: dict) -> float | None:
    """Today's volume against its own 3-month average."""
    vol = quote.get("regularMarketVolume")
    avg = quote.get("averageDailyVolume3Month") or quote.get("averageDailyVolume10Day")
    if not vol or not avg:
        return None
    return float(vol) / float(avg)


def screen(force: bool = False, relax_float: bool = False,
           max_price: float | None = None, min_rvol: float | None = None,
           min_volume: int | None = None, max_float: int | None = None,
           max_cap: int | None = None) -> dict:
    """Run the five filters across the market.

    relax_float keeps names whose float Yahoo does not report. Off by default:
    float is the filter doing the real work here, so passing a name because the
    number is missing would quietly turn this into a different screen.
    """
    if settings.DATA_MODE == "mock":
        return {"results": [], "note": "mock data — screen not run"}

    # Every threshold is overridable, so tightening back toward the stated
    # screen is a query parameter rather than a code change.
    px_max = max_price if max_price is not None else MAX_PRICE
    rv_min = min_rvol if min_rvol is not None else MIN_RVOL
    vol_min = min_volume if min_volume is not None else MIN_VOLUME
    flt_max = max_float if max_float is not None else MAX_FLOAT
    cap_max = max_cap if max_cap is not None else MAX_CAP

    key = f"lowfloat:{relax_float}:{px_max}:{rv_min}:{vol_min}:{flt_max}:{cap_max}"
    hit = _CACHE.get(key)
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return {"results": hit[1], "cached": True, "filters": describe()}

    rows: dict[str, dict] = {}
    scanned = 0
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q

        # Push every filter Yahoo can evaluate server-side into the query, so
        # what comes back is already close. Float is not queryable, so it is
        # applied below.
        custom = Q("and", [
            Q("lt", ["intradayprice", px_max]),
            Q("gt", ["dayvolume", vol_min]),
            Q("lt", ["intradaymarketcap", cap_max]),
        ])
        # most_actives catches names the custom query's field coverage misses.
        for src in (custom, "most_actives", "small_cap_gainers"):
            try:
                kw = {"count": 100}
                if not isinstance(src, str):
                    kw.update(sortField="dayvolume", sortAsc=False)
                res = yf.screen(src, **kw)
                quotes = res.get("quotes", []) if isinstance(res, dict) else []
                scanned += len(quotes)
                for q in quotes:
                    sym = q.get("symbol")
                    if sym:
                        rows.setdefault(sym, q)
            except Exception as exc:
                print(f"[lowfloat] screener {src!r} failed: {exc!r}")
    except Exception as exc:
        return {"results": [], "note": f"screener unavailable: {exc}",
                "filters": describe()}

    out: list[dict] = []
    for sym, q in rows.items():
        # US listings only. Yahoo's most_actives happily returns foreign lines
        # (a Hong Kong ticker with a 2.7 BILLION share float came back on the
        # first live run), and a screen about float discipline cannot include
        # markets whose share counts and hours are a different game.
        if "." in sym or "-" in sym:
            continue
        exch = str(q.get("fullExchangeName") or q.get("exchange") or "")
        if exch and not any(k in exch for k in ("NASDAQ", "NYSE", "NYSEAmerican",
                                                "AMEX", "NasdaqGS", "NasdaqCM",
                                                "NasdaqGM", "NYSEArca")):
            continue
        if str(q.get("currency") or "USD").upper() != "USD":
            continue
        price = q.get("regularMarketPrice")
        vol = q.get("regularMarketVolume")
        cap = q.get("marketCap")
        if price is None or price >= px_max:
            continue
        if not vol or vol < vol_min:
            continue
        if cap is None or cap >= cap_max:
            continue
        rv = _rvol(q)
        if rv is None or rv < rv_min:
            continue

        # Float needs a per-symbol fetch; only the survivors are worth it.
        flt = None
        try:
            from . import market_data
            md = market_data.get_market_data(sym)
            flt = (md.structure or {}).get("float_shares")
        except Exception:
            flt = None

        if flt is None and not relax_float:
            continue
        if flt is not None and flt >= flt_max:
            continue

        turnover = (vol / flt) if flt else None
        out.append({
            "symbol": sym,
            "name": q.get("shortName") or q.get("longName") or sym,
            "price": round(float(price), 2),
            "change_pct": round(float(q.get("regularMarketChangePercent") or 0), 2),
            "volume": int(vol),
            "rvol": round(rv, 2),
            "float_shares": int(flt) if flt else None,
            "float_unknown": flt is None,
            "market_cap": int(cap),
            # The number the whole screen is really about: how much of the
            # tradeable supply changed hands today.
            "float_turnover": round(turnover, 2) if turnover else None,
        })

    out.sort(key=lambda r: -(r["float_turnover"] or r["rvol"]))
    _CACHE[key] = (time.time(), out)
    return {"results": out, "scanned": scanned, "cached": False,
            "filters": describe(px_max, rv_min, vol_min, flt_max, cap_max)}


def describe(px=None, rv=None, vol=None, flt=None, cap=None) -> dict:
    flt = flt if flt is not None else MAX_FLOAT
    return {
        "max_price": px if px is not None else MAX_PRICE,
        "min_rvol": rv if rv is not None else MIN_RVOL,
        "min_volume": vol if vol is not None else MIN_VOLUME,
        "max_float": flt,
        "max_market_cap": cap if cap is not None else MAX_CAP,
        "stated": STATED,
        "loosened_from_stated": flt > STATED["max_float"],
        "calibration": ("float<20M as stated returned a name on 5% of sessions "
                        "over a 90-day replay. Float is the only filter that "
                        "moves the count; volume and rvol barely do. 150M lands "
                        "~1.5 names/day with 70% of days in the 1-5 band."),
        "honest_cost": ("At a 150M float ceiling this is no longer a LOW-float "
                        "screen — it is a high-turnover screen with a float "
                        "cap. The squeeze mechanics that justified the original "
                        "20M are much weaker here."),
        "caveat": ("A screen shortens a list; it is not an edge. Float is the "
                   "filter carrying the thesis and the least reliable field — "
                   "it goes stale after offerings, which these names do "
                   "constantly."),
    }
