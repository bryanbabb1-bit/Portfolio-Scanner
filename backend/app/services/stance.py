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

# A call is STICKY: it only changes when something material actually happened.
# Nothing changes in a 5-minute span, so the call shouldn't either.
MATERIAL_PCT = 0.04      # a >=4% move since the call = "something changed"
STABILITY_HOURS = 8      # a call holds through the session absent a trigger


def is_stable(symbol: str, current_price=None, *, deep: bool = False) -> bool:
    """True when the standing call should be HELD, not re-derived — it's recent,
    fresh research isn't being pulled, and price hasn't moved materially since.
    False means there's a legitimate reason to reconsider (stale, deep research,
    or a real move)."""
    s = get(symbol)
    if not s:
        return False          # no call yet — one must be formed
    if deep:
        return False          # pulling live research is a real reason to revisit
    if (time.time() - float(s.get("ts", 0))) / 3600 > STABILITY_HOURS:
        return False          # gone stale — re-derive
    anchor = s.get("price")
    if anchor and current_price:
        if abs(current_price - anchor) / anchor >= MATERIAL_PCT:
            return False      # material move — reconsideration allowed
    return True               # nothing material changed — hold the line


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


def block(symbol: str, current_price=None) -> str:
    """Prompt block stating the standing call for one symbol, demanding
    consistency. When current_price is given it spells out the move since the
    call and, if immaterial, hard-orders the model to keep the call. Empty
    string if no prior call exists."""
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

    move_line = ""
    if current_price and s.get("price"):
        mv = (current_price - s["price"]) / s["price"] * 100
        if abs(mv) < MATERIAL_PCT * 100:
            move_line = (
                f"Since that call {s['symbol']} is ${current_price:.2f} "
                f"({mv:+.1f}%) — IMMATERIAL. Nothing has changed. Return exactly "
                f"{s['action']}; do NOT flip the call.\n")
        else:
            move_line = (
                f"Since that call {s['symbol']} is ${current_price:.2f} "
                f"({mv:+.1f}%) — a MATERIAL move; reconsidering the call is "
                f"warranted if the data supports it.\n")

    return (
        f"YOUR STANDING CALL on {s['symbol']} as of {s['as_of']}{at}: "
        f"{s['action']} — {thesis}.{lvls}\n{move_line}"
        f"You already told the client this. Do NOT change the call unless you can "
        f"cite a SPECIFIC new fact: a >~4% price move, a level break, or fresh "
        f"news/earnings. A refresh with no new information must return the SAME "
        f"call. If you do change it, open with 'Changing my call on {s['symbol']} "
        f"from {s['action']} to <X> because <fact>'. Never silently flip.\n\n"
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
