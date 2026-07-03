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


@router.get("/scorecard")
def scorecard():
    """How the engine's calls have performed: per-rule win rate and average
    forward return (sign-adjusted for sells). Advice is only good if it's
    right — this is the receipts."""
    from ..services import scorecard as scorecard_service
    try:
        return scorecard_service.compute()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Scorecard failed: {exc}")


@router.post("/signals/dismiss")
def dismiss_signals(id: str | None = None):
    """Dismiss one signal by id, or every active signal when id is omitted.
    A new fire (new rule or post-cooldown re-fire) mints a new id and shows
    again — dismissal never mutes future signals."""
    return {"dismissed": conviction.dismiss(id)}
