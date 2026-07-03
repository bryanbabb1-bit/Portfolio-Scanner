"""Strategy mode endpoints — plan generation, persistence, approval."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..models.schemas import StrategyGenRequest
from ..services import strategy as strategy_service

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("")
def get_strategy():
    """The current strategy document (404 until one is generated)."""
    doc = strategy_service.load()
    if not doc:
        raise HTTPException(status_code=404, detail="no strategy yet")
    return doc


@router.post("/generate")
def generate_strategy(req: StrategyGenRequest):
    """Draft (or revise) the two-horizon strategy with the best model.
    deep=true adds live web research first."""
    try:
        return strategy_service.generate(req.model_dump(), deep=req.deep)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Strategy failed: {exc}")


@router.put("")
def save_strategy(doc: dict):
    """Persist client edits / approval. approved=true activates the plan —
    every subsequent brief aligns to it."""
    if not isinstance(doc, dict) or "thesis" not in doc:
        raise HTTPException(status_code=422, detail="not a strategy document")
    return strategy_service.save(doc)
