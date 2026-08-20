"""Catalyst map — late-stage trials on held names, and their listed partners."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import catalysts as catalyst_service

router = APIRouter(prefix="/api", tags=["catalysts"])


@router.get("/catalysts")
def catalyst_map(force: bool = False):
    """The map. Cached for a day — the registry does not move faster."""
    try:
        return catalyst_service.get(force=force)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Catalyst map failed: {exc}")
