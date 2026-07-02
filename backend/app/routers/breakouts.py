"""Breakout radar — live pulse on stocks poised to break out."""
from __future__ import annotations

from fastapi import APIRouter

from ..services import market_data, screener, themes
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api", tags=["breakouts"])


@router.get("/breakouts")
def breakouts(min_score: float = 0.0, limit: int = 20):
    """Rank the full universe by breakout-readiness score (0-100)."""
    pf = pf_service.load_portfolio()
    universe = list(pf.get("holdings", [])) + pf.get("watchlist", [])

    market_data.warm_cache([i["symbol"] for i in universe])
    seen: set[str] = set()
    cands = []
    for item in universe:
        sym = item["symbol"].upper()
        if sym in seen:
            continue
        seen.add(sym)
        try:
            md = market_data.get_market_data(sym)
            cands.append(screener.evaluate(
                sym, themes.resolve(sym, item.get("theme")), md))
        except Exception as exc:  # one bad ticker must not kill the radar
            print(f"[breakouts] skipping {sym}: {exc!r}")

    cands = [c for c in cands if c.score >= min_score]
    cands.sort(key=lambda c: c.score, reverse=True)
    source = "mock" if any(c.quote.source == "mock" for c in cands) else "live"
    return {"count": len(cands), "source": source, "results": cands[:limit]}
