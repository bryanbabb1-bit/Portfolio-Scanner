"""Pinned actions — persist advisor recommendations the user wants to keep.

Chat threads and notes are ephemeral; a pin survives refreshes, restarts and
devices (stored server-side in data/pinned.json). Pins carry a status so a
recommendation can be checked off once acted on.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "pinned.json"
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        with open(_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_FILE, "w") as f:
        json.dump(items, f, indent=2)


def list_pins() -> list[dict]:
    items = _load()
    # Open items first, newest first within each group.
    return sorted(items, key=lambda p: (p.get("status") == "done", -p.get("ts", 0)))


def add(symbol: str | None, source: str, text: str,
        points: list[str] | None = None) -> dict:
    with _lock:
        items = _load()
        # Same text pinned twice is a double-click, not a second reminder.
        for p in items:
            if p["text"] == text and p.get("symbol") == symbol:
                return p
        sym = (symbol or "").upper() or None
        # Baseline price the moment the plan is staged — Plan Watch compares
        # against this to know when the premise has moved.
        base = None
        if sym:
            try:
                from . import portfolio as pf
                base = round(float(pf.build_report(sym).quote.price), 2)
            except Exception:
                base = None
        pin = {
            "id": uuid.uuid4().hex[:12],
            "symbol": sym,
            "source": source,
            "text": text.strip(),
            "points": [str(x).strip() for x in (points or []) if str(x).strip()],
            "status": "open",
            "price_at_pin": base,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
        }
        items.append(pin)
        _save(items)
        return pin


def patch(pin_id: str, **fields) -> dict | None:
    """Persist arbitrary fields on a pin (used by Plan Watch for baseline /
    cooldown state). Never touches text/status here."""
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pin_id:
                p.update(fields)
                _save(items)
                return p
    return None


def update(pin_id: str, status: str) -> dict | None:
    updated = None
    newly_done = False
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pin_id:
                # Only the open->done TRANSITION is an action taken. Re-marking
                # an already-done pin must NOT re-journal (that spammed ~45
                # duplicate 'acted on advice' entries and poisoned the advisor).
                newly_done = status == "done" and p.get("status") != "done"
                p["status"] = status
                p["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S") \
                    if status == "done" else None
                _save(items)
                updated = p
                break
    if updated and newly_done:
        from . import journal
        journal.add_entry(updated.get("symbol"), "note",
                          f"Acted on pinned advice: {updated['text']}",
                          source="pin")
    return updated


def delete(pin_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [p for p in items if p["id"] != pin_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True
