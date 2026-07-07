"""Action journal — a persistent, user-editable record of trades and moves.

Structured entries: date, symbol, action (buy | sell | note), shares, price,
note, source (auto | manual | pin). Auto entries come from diffing the
holdings snapshot on every portfolio read; manual entries let the user record
moves the app didn't see (and edit/delete anything). The journal is shown on
the dashboard and injected into advisor facts so guidance acknowledges
progress and frames the NEXT step, not a restart.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ..config import settings

_JOURNAL_FILE = settings.PORTFOLIO_FILE.parent / "action_journal.json"
_SNAPSHOT_FILE = settings.PORTFOLIO_FILE.parent / "holdings_snapshot.json"
_lock = threading.Lock()

VALID_ACTIONS = {"buy", "sell", "note"}

# Legacy free-text action names -> structured actions (one-time migration).
_LEGACY_ACTIONS = {"opened": "buy", "added": "buy", "trimmed": "sell",
                   "sold": "sell", "completed": "note"}


def _migrate(e: dict) -> dict:
    if e.get("action") in VALID_ACTIONS and "note" in e:
        return e
    return {
        "id": e.get("id") or uuid.uuid4().hex[:12],
        "date": (e.get("date") or "")[:10] or time.strftime("%Y-%m-%d"),
        "symbol": e.get("symbol"),
        "action": _LEGACY_ACTIONS.get(e.get("action"), "note"),
        "shares": e.get("shares"),
        "price": e.get("price"),
        "note": e.get("note") or e.get("detail") or "",
        "source": e.get("source", "auto"),
        "ts": e.get("ts", time.time()),
    }


def _load() -> list[dict]:
    try:
        with open(_JOURNAL_FILE) as f:
            data = json.load(f)
        return [_migrate(e) for e in data] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    _JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_JOURNAL_FILE, "w") as f:
        json.dump(items[-300:], f, indent=2)


def add_entry(symbol: str | None, action: str, note: str,
              shares: float | None = None, price: float | None = None,
              date: str | None = None, source: str = "auto") -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "date": (date or time.strftime("%Y-%m-%d"))[:10],
        "symbol": (symbol or "").upper().strip() or None,
        "action": action if action in VALID_ACTIONS else "note",
        "shares": shares,
        "price": price,
        "note": (note or "").strip(),
        "source": source,  # auto | manual | pin
        "ts": time.time(),
    }
    with _lock:
        items = _load()
        # Dedup: an identical note for the same symbol from an automated source
        # is a duplicate, not a second event — never spam the ledger.
        if source in ("pin", "auto") and entry["note"]:
            for e in items:
                if (e.get("symbol") == entry["symbol"]
                        and e.get("note") == entry["note"]
                        and e.get("source") == source):
                    return e
        items.append(entry)
        _save(items)
    return entry


def update_entry(entry_id: str, fields: dict) -> dict | None:
    allowed = {"date", "symbol", "action", "shares", "price", "note"}
    with _lock:
        items = _load()
        for e in items:
            if e["id"] == entry_id:
                for k, v in fields.items():
                    if k not in allowed or v is None:
                        continue
                    if k == "symbol":
                        v = (str(v).upper().strip() or None)
                    if k == "action" and v not in VALID_ACTIONS:
                        continue
                    if k == "date":
                        v = str(v)[:10]
                    e[k] = v
                _save(items)
                return e
    return None


def delete_entry(entry_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [e for e in items if e["id"] != entry_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def list_entries(days: int = 30) -> list[dict]:
    cutoff = time.strftime("%Y-%m-%d",
                           time.localtime(time.time() - days * 86400))
    items = [e for e in _load() if e.get("date", "") >= cutoff]
    return sorted(items, key=lambda e: (e.get("date", ""), e.get("ts", 0)),
                  reverse=True)


def snapshot_and_diff(holdings: list[dict]) -> list[dict]:
    """Compare current holdings to the last snapshot; journal any trades.

    First run just records the baseline silently. Share deltas under 0.5%
    are ignored (float noise / DRIP dust).
    """
    current = {h["symbol"].upper(): float(h.get("shares", 0) or 0)
               for h in holdings if h.get("symbol")}
    trades: list[tuple] = []
    with _lock:
        try:
            with open(_SNAPSHOT_FILE) as f:
                prev = json.load(f)
            prev = prev if isinstance(prev, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            prev = {}
        _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
    if not prev:
        return []

    for sym, shares in current.items():
        old = float(prev.get(sym, 0))
        if old == 0 and shares > 0:
            trades.append((sym, "buy", shares, f"Opened a new position"))
        elif shares > old and old > 0 and (shares - old) / old > 0.005:
            trades.append((sym, "buy", round(shares - old, 4),
                           f"Added shares ({old:g} -> {shares:g})"))
        elif shares < old and old > 0 and (old - shares) / old > 0.005:
            trades.append((sym, "sell", round(old - shares, 4),
                           f"Trimmed ({old:g} -> {shares:g})"))
    for sym, old in prev.items():
        if old > 0 and current.get(sym, 0) == 0:
            trades.append((sym, "sell", old, "Closed the position entirely"))

    return [add_entry(sym, action, note, shares=qty, source="auto")
            for sym, action, qty, note in trades]


def facts_block(days: int = 30, limit: int = 20) -> str:
    """Journal formatted for advisor prompts; empty string when no history."""
    entries = list_entries(days)[:limit]
    if not entries:
        return ""
    lines = [f"Actions the client has ALREADY TAKEN (last {days} days, newest first):"]
    for e in entries:
        sym = e["symbol"] or "PORTFOLIO"
        qty = f" {e['shares']:g} shares" if e.get("shares") else ""
        px = f" @ ${e['price']:g}" if e.get("price") else ""
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"  {e['date']}: {e['action'].upper()} {sym}{qty}{px}{note}")
    return "\n".join(lines)
