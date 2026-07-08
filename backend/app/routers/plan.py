"""Sequenced game plan — the reconciled, gated view of every staged move."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import plan as plan_service

router = APIRouter(prefix="/api", tags=["plan"])


@router.get("/plan")
def game_plan():
    try:
        return plan_service.build_plan()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Plan build failed: {exc}")
