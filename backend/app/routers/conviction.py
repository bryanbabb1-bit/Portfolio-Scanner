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


@router.post("/signals/dismiss")
def dismiss_signals(id: str | None = None):
    """Dismiss one signal by id, or every active signal when id is omitted.
    A new fire (new rule or post-cooldown re-fire) mints a new id and shows
    again — dismissal never mutes future signals."""
    return {"dismissed": conviction.dismiss(id)}
