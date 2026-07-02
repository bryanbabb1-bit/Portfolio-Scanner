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
        pin = {
            "id": uuid.uuid4().hex[:12],
            "symbol": (symbol or "").upper() or None,
            "source": source,
            "text": text.strip(),
            "points": [str(x).strip() for x in (points or []) if str(x).strip()],
            "status": "open",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
        }
        items.append(pin)
        _save(items)
        return pin


def update(pin_id: str, status: str) -> dict | None:
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pin_id:
                p["status"] = status
                p["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S") \
                    if status == "done" else None
                _save(items)
                return p
    return None


def delete(pin_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [p for p in items if p["id"] != pin_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True
