"""Runner Radar endpoint — explosive low-float setups (the MGRT pattern)."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import runner

router = APIRouter(prefix="/api", tags=["runner"])


@router.get("/runners")
def runners(min_score: float = 0.0, limit: int = 40, extra: str = ""):
    """Score the curated low-float / high-velocity universe (+ comma-separated
    `extra` tickers the user is watching) on explosive-setup DNA."""
    try:
        tickers = [t for t in extra.split(",") if t.strip()]
        return runner.radar(min_score=min_score, limit=limit, extra=tickers)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Runner radar failed: {exc}")


@router.get("/lowfloat")
def low_float_screen(force: bool = False, relax_float: bool = False):
    """The five-filter low-float momentum screen, run across the market."""
    from ..services import lowfloat
    return lowfloat.screen(force=force, relax_float=relax_float)
