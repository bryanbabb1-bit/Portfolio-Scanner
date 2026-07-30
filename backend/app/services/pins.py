"""Pinned actions — persist advisor recommendations the user wants to keep.

Chat threads and notes are ephemeral; a pin survives refreshes, restarts and
devices (stored server-side in data/pinned.json). Pins carry a status so a
recommendation can be checked off once acted on.
"""
from __future__ import annotations

import json
import re
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
        # Same text pinned twice is a double-click, not a second reminder —
        # but if the earlier copy was completed/cleared, re-pinning means the
        # user wants it back as an active reminder, so revive it instead of
        # silently swallowing the pin.
        for p in items:
            if p["text"] == text and p.get("symbol") == symbol:
                if p.get("status") != "open":
                    p["status"] = "open"
                    p["done_at"] = None
                    p["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    p["ts"] = time.time()
                    _save(items)
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


_EXIT_VERBS = ("sell", "trim", "close", "exit", "dump", "liquidate", "unload")


def retire_for_symbol(symbol: str, reason: str = "position closed") -> list[str]:
    """Stand down open pins that tell the client to exit a position they no
    longer hold. Returns the ids retired.

    Deliberately conservative, because retiring a pin the client still needs is
    worse than leaving a stale one. A pin is only retired when it is explicitly
    tagged with the symbol, or when BOTH:

      * the FIRST ticker-shaped token in its text is that symbol — the subject of
        the instruction, rather than a ticker named in a trailing condition, and
      * the text carries an exit verb.

    So "Sell all $152 GEV at market" retires, while
    "Buy $150 VRT near $243 (when GEV proceeds settle)" survives: its subject is
    VRT and the GEV clause is a precondition that just came true.

    Any unrecognised token in the subject slot blocks retirement rather than being
    skipped over — "Sell SPMO once GEV proceeds land" is about SPMO, and reading
    past it to find GEV would cancel a live order. Every ambiguity here resolves
    toward leaving the pin alone.
    """
    sym = (symbol or "").upper()
    if not sym:
        return []
    retired: list[str] = []
    with _lock:
        items = _load()
        for p in items:
            if p.get("status") != "open":
                continue
            text = p.get("text") or ""
            tagged = (p.get("symbol") or "").upper() == sym
            if not tagged:
                found = re.findall(r"\b[A-Z][A-Z.\-]{0,5}\b", text)
                subject = found[0] if found else None
                has_exit = any(v in text.lower() for v in _EXIT_VERBS)
                if subject != sym or not has_exit:
                    continue
            p["status"] = "done"
            p["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            p["retired_reason"] = reason
            retired.append(p["id"])
        if retired:
            _save(items)
    # No "acted on pinned advice" journal note here: the journal is already
    # recording the sell that triggered this, and a second entry would claim the
    # client worked a checklist they never touched.
    return retired


def delete(pin_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [p for p in items if p["id"] != pin_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True
