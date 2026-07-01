"""AI advisor endpoints (headless Claude via the local subscription)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import advisor as advisor_service
from ..services import market_data, screener
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.get("/stock/{symbol}")
def advise_stock(symbol: str, force: bool = False):
    """Senior-advisor narrative + technical read for one stock."""
    try:
        report = pf_service.build_report(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report failed: {exc}")
    return advisor_service.advise_stock(report, force=force)


@router.get("/breakout/{symbol}")
def advise_breakout(symbol: str, force: bool = False):
    """The bull case (and invalidation) for a breakout candidate."""
    md = market_data.get_market_data(symbol.upper())
    pf = pf_service.load_portfolio()
    theme = next(
        (i.get("theme") for i in pf.get("holdings", []) + pf.get("watchlist", [])
         if i["symbol"].upper() == symbol.upper()),
        None,
    )
    cand = screener.evaluate(symbol.upper(), theme, md)
    return advisor_service.advise_breakout(cand, force=force)
