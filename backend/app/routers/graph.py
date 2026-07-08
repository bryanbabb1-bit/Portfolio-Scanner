"""Relationship-graph endpoint — the holdings' correlation web."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import graph as graph_service

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
def relationship_graph():
    try:
        return graph_service.build_graph()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Graph build failed: {exc}")
