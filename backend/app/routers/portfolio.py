"""Portfolio + per-stock report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import portfolio as pf_service

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def get_portfolio():
    """Full portfolio: summary metrics + a report card per holding."""
    summary, reports = pf_service.portfolio_summary()
    return {"summary": summary, "holdings": reports}


@router.get("/config")
def get_config():
    """Raw portfolio config (holdings, watchlist, themes)."""
    return pf_service.load_portfolio()


@router.get("/stock/{symbol}")
def get_stock(symbol: str):
    """Deep report for a single symbol (held or not)."""
    try:
        return pf_service.build_report(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not build report: {exc}")
