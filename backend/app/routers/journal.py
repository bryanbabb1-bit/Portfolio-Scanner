"""Action journal CRUD — the user controls the record the advisor reads."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import JournalCreate, JournalUpdate
from ..services import journal as journal_service

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
def list_journal(days: int = 30):
    """Auto-detected trades + completed pins + manual entries."""
    items = journal_service.list_entries(days)
    return {"count": len(items), "results": items}


@router.post("")
def create_entry(req: JournalCreate):
    if req.action in ("buy", "sell") and not (req.symbol or "").strip():
        raise HTTPException(status_code=422, detail="symbol required for buy/sell")
    return journal_service.add_entry(
        req.symbol, req.action, req.note, shares=req.shares,
        price=req.price, date=req.date, source="manual")


@router.patch("/{entry_id}")
def update_entry(entry_id: str, req: JournalUpdate):
    entry = journal_service.update_entry(
        entry_id, req.model_dump(exclude_none=True))
    if not entry:
        raise HTTPException(status_code=404, detail="journal entry not found")
    return entry


@router.delete("/{entry_id}")
def delete_entry(entry_id: str):
    if not journal_service.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="journal entry not found")
    return {"deleted": entry_id}
