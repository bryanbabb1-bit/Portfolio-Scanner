"""Learning-loop endpoints: joined rule health and proposal acceptance."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import learning

router = APIRouter(prefix="/api", tags=["learning"])


@router.get("/learning")
def get_learning():
    """Per-rule health joining the live scorecard with the last replay."""
    try:
        return learning.rule_health()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Rule health failed: {exc}")


@router.post("/learning/accept/{rule}")
def accept(rule: str, note: str = ""):
    """Record that a proposal was accepted. Does NOT change what fires."""
    return learning.accept(rule, note)


@router.delete("/learning/accept/{rule}")
def unaccept(rule: str):
    return {"removed": learning.unaccept(rule)}
