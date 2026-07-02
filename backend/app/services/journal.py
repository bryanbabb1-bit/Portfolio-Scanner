"""Action journal — a persistent record of what the user has actually done.

Without this the advisor is stateless: every brief re-reads the current
snapshot and re-prescribes from scratch ("cut more") even while the user is
mid-execution. Entries come from two sources:
  - auto: diffing the holdings snapshot on every portfolio read, so trades
    mirrored into Settings (or portfolio.json) are captured with no manual work
  - pin: a pinned recommendation checked off as done
The journal is shown on the dashboard and injected into advisor facts so
guidance acknowledges progress and frames the NEXT step, not a restart.
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


def _load(path, default):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def add_entry(symbol: str | None, action: str, detail: str,
              source: str = "auto") -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "symbol": (symbol or "").upper() or None,
        "action": action,   # sold | trimmed | added | opened | completed
        "detail": detail,
        "source": source,   # auto | pin
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "ts": time.time(),
    }
    with _lock:
        items = _load(_JOURNAL_FILE, [])
        items.append(entry)
        _save(_JOURNAL_FILE, items[-200:])  # keep the journal bounded
    return entry


def list_entries(days: int = 30) -> list[dict]:
    cutoff = time.time() - days * 86400
    items = [e for e in _load(_JOURNAL_FILE, []) if e.get("ts", 0) >= cutoff]
    return sorted(items, key=lambda e: -e.get("ts", 0))


def snapshot_and_diff(holdings: list[dict]) -> list[dict]:
    """Compare current holdings to the last snapshot; journal any trades.

    First run just records the baseline silently. Share deltas under 0.5%
    are ignored (float noise / DRIP dust).
    """
    current = {h["symbol"].upper(): float(h.get("shares", 0) or 0)
               for h in holdings if h.get("symbol")}
    new_entries: list[dict] = []
    with _lock:
        prev = _load(_SNAPSHOT_FILE, {})
        _save(_SNAPSHOT_FILE, current)
    if not prev:
        return []

    def note(sym, action, detail):
        new_entries.append((sym, action, detail))

    for sym, shares in current.items():
        old = float(prev.get(sym, 0))
        if old == 0 and shares > 0:
            note(sym, "opened", f"Opened a new position: {shares:g} shares")
        elif shares > old and old > 0 and (shares - old) / old > 0.005:
            note(sym, "added", f"Added {shares - old:g} shares "
                               f"({old:g} -> {shares:g})")
        elif shares < old and old > 0 and (old - shares) / old > 0.005:
            note(sym, "trimmed", f"Trimmed {old - shares:g} shares "
                                 f"({old:g} -> {shares:g})")
    for sym, old in prev.items():
        if old > 0 and current.get(sym, 0) == 0:
            note(sym, "sold", f"Closed the position entirely ({old:g} shares)")

    return [add_entry(sym, action, detail, source="auto")
            for sym, action, detail in new_entries]


def facts_block(days: int = 30, limit: int = 15) -> str:
    """Journal formatted for advisor prompts; empty string when no history."""
    entries = list_entries(days)[:limit]
    if not entries:
        return ""
    lines = [f"Actions the client has ALREADY TAKEN (last {days} days, newest first):"]
    for e in entries:
        sym = e["symbol"] or "PORTFOLIO"
        lines.append(f"  {e['date'][:10]}: {sym} — {e['action'].upper()}: {e['detail']}")
    return "\n".join(lines)
