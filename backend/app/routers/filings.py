"""Material-event filings for the book — 8-Ks and the forms that move a stock."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import filings as filing_service

router = APIRouter(prefix="/api", tags=["filings"])


@router.get("/filings")
def recent_filings(force: bool = False, days: int = filing_service.LOOKBACK_DAYS):
    try:
        return filing_service.get(force=force, days=days)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Filings read failed: {exc}")
