"""Scan endpoint — news, trends, ratings and signals across the whole universe."""
from __future__ import annotations

from fastapi import APIRouter

from ..services import market_data
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api", tags=["scan"])


@router.get("/scan")
def scan(include_watchlist: bool = True):
    """Scan holdings (+ optional watchlist) and return compact report cards.

    This is the "hub" feed: each item carries price, key indicators, analyst
    rating/target, top headlines and derived signals.
    """
    pf = pf_service.load_portfolio()
    universe = list(pf.get("holdings", []))
    if include_watchlist:
        universe += pf.get("watchlist", [])

    market_data.warm_cache([i["symbol"] for i in universe])
    seen: set[str] = set()
    reports = []
    for item in universe:
        sym = item["symbol"].upper()
        if sym in seen:
            continue
        seen.add(sym)
        try:
            reports.append(pf_service.build_report(sym, item.get("theme")))
        except Exception as exc:  # one bad ticker must not kill the scan
            print(f"[scan] skipping {sym}: {exc!r}")

    # Sort by strongest bullish tilt so the most actionable float to the top.
    def bull_score(r):
        return sum(1 for s in r.signals if s.kind == "bullish") - \
               sum(1 for s in r.signals if s.kind == "bearish")

    reports.sort(key=bull_score, reverse=True)
    source = "mock" if any(r.quote.source == "mock" for r in reports) else "live"
    return {"count": len(reports), "source": source, "results": reports}
