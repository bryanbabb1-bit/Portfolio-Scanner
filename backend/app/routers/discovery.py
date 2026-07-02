"""Discovery endpoint — breakout-ready names you don't own yet."""
from __future__ import annotations

from fastapi import APIRouter

from ..services import discovery

router = APIRouter(prefix="/api", tags=["discovery"])


@router.get("/discover")
def discover(min_score: float = 0.0, limit: int = 24):
    """Scan the curated adjacent-universe for breakout setups not in the
    portfolio or watchlist, ranked by readiness score."""
    return discovery.discover(min_score=min_score, limit=limit)
