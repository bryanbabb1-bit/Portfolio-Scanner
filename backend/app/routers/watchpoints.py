"""Watchpoint endpoints — standing price/RSI tripwires that fire slaps."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..models.schemas import WatchpointCreate
from ..services import market_data, watchpoints
from ..services.technical import compute_indicators

router = APIRouter(prefix="/api/watchpoints", tags=["watchpoints"])


@router.get("")
def list_watchpoints():
    items = watchpoints.list_watchpoints()
    return {"count": len(items), "results": items}


@router.post("")
def create_watchpoint(req: WatchpointCreate):
    # Refuse conditions that are already true — they'd slap instantly.
    try:
        md = market_data.get_price_data(req.symbol.upper())
        ind = compute_indicators(md.history)
        price = float(md.history["Close"].iloc[-1])
        if watchpoints.already_true(req.symbol, req.kind, req.level,
                                    price, ind.rsi):
            raise HTTPException(
                status_code=422,
                detail=f"That condition is already true right now "
                       f"(price ${price:g}, RSI {ind.rsi:g}) — set a level "
                       f"beyond the current reading.")
    except HTTPException:
        raise
    except Exception:
        pass  # can't fetch a reading — arm it anyway
    return watchpoints.add(req.symbol, req.kind, req.level,
                           note=req.note, side=req.side, source="manual")


@router.delete("/{wp_id}")
def delete_watchpoint(wp_id: str):
    if not watchpoints.delete(wp_id):
        raise HTTPException(status_code=404, detail="watchpoint not found")
    return {"deleted": wp_id}


@router.post("/extract")
def extract():
    """Mine the latest brief + active strategy for conditional advice and
    arm the concrete conditions as watchpoints."""
    try:
        created = watchpoints.extract_from_advice()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Extraction failed: {exc}")
    return {"created": len(created), "results": created}
