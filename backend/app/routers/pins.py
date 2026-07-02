"""Pinned advisor actions — CRUD for the dashboard's persistent action list."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import PinCreate, PinUpdate
from ..services import pins as pin_service

router = APIRouter(prefix="/api/pins", tags=["pins"])


@router.get("")
def list_pins():
    items = pin_service.list_pins()
    return {"count": len(items), "results": items}


@router.post("")
def create_pin(req: PinCreate):
    return pin_service.add(req.symbol, req.source, req.text, req.points)


@router.patch("/{pin_id}")
def update_pin(pin_id: str, req: PinUpdate):
    pin = pin_service.update(pin_id, req.status)
    if not pin:
        raise HTTPException(status_code=404, detail="pin not found")
    return pin


@router.delete("/{pin_id}")
def delete_pin(pin_id: str):
    if not pin_service.delete(pin_id):
        raise HTTPException(status_code=404, detail="pin not found")
    return {"deleted": pin_id}
