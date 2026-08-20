"""Whole-market big movers — the watch that ignores the book and the cash."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import bigmoves as bigmove_service

router = APIRouter(prefix="/api", tags=["bigmoves"])


@router.get("/bigmoves")
def big_moves(force: bool = False):
    """What the last heartbeat scan saw. `force=1` rescans on demand."""
    try:
        if force:
            bigmove_service.scan(force=True)
        return bigmove_service.latest()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Big-move scan failed: {exc}")
