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

# Kev's five, exactly as stated. Named so a change is a decision, not a drift.
MAX_PRICE = 20.0
MIN_RVOL = 2.0
MIN_VOLUME = 4_000_000
MAX_FLOAT = 20_000_000
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


def screen(force: bool = False, relax_float: bool = False) -> dict:
    """Run the five filters across the market.

    relax_float keeps names whose float Yahoo does not report. Off by default:
    float is the filter doing the real work here, so passing a name because the
    number is missing would quietly turn this into a different screen.
    """
    if settings.DATA_MODE == "mock":
        return {"results": [], "note": "mock data — screen not run"}

    key = f"lowfloat:{relax_float}"
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
            Q("lt", ["intradayprice", MAX_PRICE]),
            Q("gt", ["dayvolume", MIN_VOLUME]),
            Q("lt", ["intradaymarketcap", MAX_CAP]),
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
        if price is None or price >= MAX_PRICE:
            continue
        if not vol or vol < MIN_VOLUME:
            continue
        if cap is None or cap >= MAX_CAP:
            continue
        rv = _rvol(q)
        if rv is None or rv < MIN_RVOL:
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
        if flt is not None and flt >= MAX_FLOAT:
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
            "filters": describe()}


def describe() -> dict:
    return {
        "max_price": MAX_PRICE,
        "min_rvol": MIN_RVOL,
        "min_volume": MIN_VOLUME,
        "max_float": MAX_FLOAT,
        "max_market_cap": MAX_CAP,
        "caveat": ("A screen shortens a list; it is not an edge. Float is the "
                   "filter carrying the thesis and the least reliable field — "
                   "it goes stale after offerings, which these names do "
                   "constantly."),
    }
