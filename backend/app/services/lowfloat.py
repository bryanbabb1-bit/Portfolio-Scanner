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

# Float is back to the stated 20M. An earlier calibration concluded it had to be
# loosened to 150M to fire at all — that conclusion was drawn from a 90-name
# sample, and it was wrong. Against the real 2,000-name universe the stated
# screen returns ~24 names a day:
#
#   float<20M    24 names   <- as stated
#   float<50M    30
#   float<150M   39
#
# Loosening float was solving a problem that only existed because the universe
# was too small to see. The thesis stays intact.
MAX_PRICE = 20.0
MIN_RVOL = 2.0
MIN_VOLUME = 4_000_000
MAX_FLOAT = 20_000_000
MAX_CAP = 2_000_000_000

# A floor the original screen did not have, and the lever that actually gets
# from ~24 names to a handful. Measured at full coverage:
#
#   no floor   24 names        (sub-$1 churn dominates)
#   >= $1      13
#   >= $2      10
#   >= $3       5
#   >= $5       1
#
# Default is 0 — the screen runs exactly as stated. The floor is a knob, not a
# silent correction to somebody else's screen.
#
# This TIGHTENS the thesis rather than diluting it. Below a few dollars there is
# no institutional participation, halts are routine and dilution is constant, so
# a 400x rvol print is churn rather than a squeeze — the opposite of what the
# screen is hunting.
MIN_PRICE = 0.0

# Yahoo caps a screener page at 25 regardless of the count requested, so the
# whole qualifying set has to be walked. 80 pages is 2,000 names, comfortably
# past the number that clear a 4M-share volume bar on any given day.
PAGE_SIZE = 25
MAX_PAGES = 80

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
           max_price: float | None = None, min_price: float | None = None,
           min_rvol: float | None = None,
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
    px_min = min_price if min_price is not None else MIN_PRICE
    rv_min = min_rvol if min_rvol is not None else MIN_RVOL
    vol_min = min_volume if min_volume is not None else MIN_VOLUME
    flt_max = max_float if max_float is not None else MAX_FLOAT
    cap_max = max_cap if max_cap is not None else MAX_CAP

    key = (f"lowfloat:{relax_float}:{px_max}:{px_min}:{rv_min}:{vol_min}:"
           f"{flt_max}:{cap_max}")
    hit = _CACHE.get(key)
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return {"results": hit[1], "cached": True, "filters": describe()}

    rows: dict[str, dict] = {}
    scanned = 0
    total_available = None
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q

        # Every filter Yahoo can evaluate goes server-side, so what comes back
        # already satisfies four of the five. Float is not queryable and is
        # applied below, per surviving symbol.
        custom = Q("and", [
            Q("lt", ["intradayprice", px_max]),
            Q("gt", ["intradayprice", px_min]),
            Q("gt", ["dayvolume", vol_min]),
            Q("lt", ["intradaymarketcap", cap_max]),
        ])

        # PAGINATE. A single call returns 25 rows out of thousands — reading
        # only the first page meant screening a keyhole and calling it the
        # market. Yahoo reports `total`, so coverage is measurable rather than
        # assumed, and the walk continues until the qualifying set is exhausted.
        offset = 0
        for _ in range(MAX_PAGES):
            try:
                res = yf.screen(custom, count=PAGE_SIZE, offset=offset,
                                sortField="dayvolume", sortAsc=False)
            except Exception as exc:
                print(f"[lowfloat] page at offset {offset} failed: {exc!r}")
                break
            quotes = res.get("quotes", []) if isinstance(res, dict) else []
            if total_available is None:
                total_available = res.get("total")
            if not quotes:
                break
            scanned += len(quotes)
            before = len(rows)
            for q in quotes:
                sym = q.get("symbol")
                if sym:
                    rows.setdefault(sym, q)
            if len(rows) == before:
                break                     # same page repeating; stop
            offset += len(quotes)
            if total_available and offset >= total_available:
                break
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
        if price is None or price >= px_max or price < px_min:
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
    return {"results": out, "scanned": scanned,
            "universe_total": total_available,
            # Honest coverage: what fraction of the qualifying landscape was
            # actually looked at. A screen that silently sees 2% of the market
            # is worse than one that says so.
            "coverage_pct": (round(scanned / total_available * 100, 1)
                             if total_available else None),
            "cached": False,
            "filters": describe(px_max, rv_min, vol_min, flt_max, cap_max)}


def describe(px=None, rv=None, vol=None, flt=None, cap=None) -> dict:
    flt = flt if flt is not None else MAX_FLOAT
    return {
        "max_price": px if px is not None else MAX_PRICE,
        "min_price": MIN_PRICE,
        "min_rvol": rv if rv is not None else MIN_RVOL,
        "min_volume": vol if vol is not None else MIN_VOLUME,
        "max_float": flt,
        "max_market_cap": cap if cap is not None else MAX_CAP,
        "stated": STATED,
        "loosened_from_stated": flt > STATED["max_float"],
        "calibration": ("Against the full ~2,000-name qualifying universe the "
                        "screen as stated returns ~24 names a day. An earlier "
                        "run suggested float had to be loosened to 150M to fire "
                        "at all; that came from a 90-name sample and was wrong. "
                        "Float is unchanged at 20M."),
        "narrowing": ("The way down to a handful is a $1 price floor, not a "
                      "looser float. About a third of what passes is sub-$1, "
                      "where a 400x rvol print is churn rather than a squeeze."),
        "caveat": ("A screen shortens a list; it is not an edge. Float is the "
                   "filter carrying the thesis and the least reliable field — "
                   "it goes stale after offerings, which these names do "
                   "constantly."),
    }
