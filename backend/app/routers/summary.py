"""Daily brief endpoint — morning 'what to watch' + end-of-day recap."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import summary as summary_service

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary")
def get_summary():
    """The latest daily brief (morning or close recap) + its dismissed state."""
    return summary_service.latest_state()


@router.post("/summary/dismiss")
def dismiss_summary():
    """Mark the current brief read — hides until the next one posts."""
    return summary_service.dismiss()


@router.post("/summary/generate")
def generate(kind: str = "morning"):
    """Generate a brief on demand (kind = morning | eod). Also pushes it."""
    if kind not in ("morning", "eod"):
        raise HTTPException(status_code=400, detail="kind must be 'morning' or 'eod'")
    try:
        return summary_service.maybe_send_daily(force_kind=kind)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Brief failed: {exc}")
