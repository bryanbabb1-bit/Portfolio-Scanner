"""Unusual-volume screen — where size showed up before the move."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import accumulation as acc_service

router = APIRouter(prefix="/api", tags=["accumulation"])


@router.get("/accumulation")
def accumulation(force: bool = False):
    try:
        return acc_service.get(force=force)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Accumulation scan failed: {exc}")
