"""Advisor stance ledger — the advisor's MEMORY of its current call on each
symbol, so every surface speaks with ONE voice.

Without this, the whole-book brief, the single-stock review, the notification
recommendation and the chat are each an independent Claude call with no shared
state — so the brief can say SELL while the stock review says HOLD. Every
surface now reads the standing call (via block()/book_block()) and is told to
stay consistent with it or flag a change explicitly; surfaces that form a clean
per-symbol call write it back with set_stance(). One source of truth.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "advisor_stances.json"
_lock = threading.Lock()
_VALID = {"BUY", "ADD", "TRIM", "SELL", "HOLD", "AVOID", "WATCH"}


def _load() -> dict:
    try:
        with open(_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(d: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_FILE, "w") as f:
        json.dump(d, f, indent=2)


def get(symbol: str) -> dict | None:
    return _load().get((symbol or "").upper())


def all_stances() -> dict:
    return _load()


def _norm(action: str | None) -> str:
    a = str(action or "").upper().strip().split()[0] if action else "HOLD"
    return a if a in _VALID else "HOLD"


def set_stance(symbol: str, action: str | None, *, headline: str = "",
               thesis: str = "", target: str = "", stop: str = "",
               source: str = "", price=None) -> dict:
    """Upsert the current call for a symbol. Returns the stored stance."""
    sym = (symbol or "").upper()
    if not sym:
        return {}
    prev = get(sym)
    with _lock:
        d = _load()
        d[sym] = {
            "symbol": sym,
            "action": _norm(action),
            "prev_action": prev.get("action") if prev else None,
            "headline": str(headline or "")[:140],
            "thesis": str(thesis or "")[:400],
            "target": str(target or ""),
            "stop": str(stop or ""),
            "source": source,
            "price": price,
            "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
        }
        _save(d)
        return d[sym]


def block(symbol: str) -> str:
    """Prompt block stating the standing call for one symbol, demanding
    consistency. Empty string if no prior call exists."""
    s = get(symbol)
    if not s:
        return ""
    lvl = []
    if s.get("target"):
        lvl.append(f"target {s['target']}")
    if s.get("stop"):
        lvl.append(f"stop {s['stop']}")
    lvls = (" " + "; ".join(lvl) + ".") if lvl else ""
    at = f" (called when it was ${s['price']})" if s.get("price") else ""
    thesis = s.get("thesis") or s.get("headline") or ""
    return (
        f"YOUR STANDING CALL on {s['symbol']} as of {s['as_of']}{at}: "
        f"{s['action']} — {thesis}.{lvls}\n"
        f"You already told the client this. Stay CONSISTENT with it. Only change "
        f"the call if the data has MATERIALLY moved since; if so, open with "
        f"'Changing my call on {s['symbol']} from {s['action']} to <X>' and give "
        f"the reason. Never silently contradict your own prior call.\n\n"
    )


def book_block(symbols: list[str]) -> str:
    """Compact list of standing calls across a set of holdings, for the brief."""
    d = _load()
    rows = []
    for sym in symbols:
        s = d.get((sym or "").upper())
        if s:
            tag = s.get("headline") or (s.get("thesis") or "")[:60]
            rows.append(f"- {s['symbol']}: {s['action']} ({tag}) [as of {s['as_of'][:10]}]")
    if not rows:
        return ""
    return (
        "YOUR STANDING CALLS on holdings you have already ruled on (be "
        "consistent; if you change any, flag it explicitly with the reason):\n"
        + "\n".join(rows) + "\n\n"
    )
