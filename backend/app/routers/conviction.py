"""Conviction signal endpoint — strong buy/sell alerts for the slap overlay."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import conviction

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/signals")
def signals(demo: bool = False):
    """Active conviction signals (last 48h). Detection is deterministic;
    enrichment runs once per new signal. demo=true prepends a preview signal."""
    try:
        results = conviction.scan()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Signal scan failed: {exc}")
    if demo:
        results = [conviction.demo_signal()] + results
    return {"count": len(results), "results": results}
