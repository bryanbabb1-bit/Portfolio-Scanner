"""Watchpoints — armed price/RSI tripwires that fire slap alerts.

The advisor constantly gives conditional advice ("sell half IREN below
$38.80", "buy AVGO when RSI reclaims 45"). A watchpoint turns that condition
into a standing alert: it rides the same conviction scan loop and produces a
full-screen slap the moment it triggers — no chart-stalking. Watchpoints are
created manually or extracted automatically from the advisor's own briefs
and the approved strategy. Triggering costs zero AI tokens (the advice text
IS the alert body) and writes a journal note.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "watchpoints.json"
_lock = threading.Lock()

KINDS = {"price_below", "price_above", "rsi_below", "rsi_above"}


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
        json.dump(items[-200:], f, indent=2)


def condition_str(wp: dict) -> str:
    metric = "RSI" if wp["kind"].startswith("rsi") else "price"
    op = "≤" if wp["kind"].endswith("below") else "≥"
    lvl = f"${wp['level']:g}" if metric == "price" else f"{wp['level']:g}"
    return f"{metric} {op} {lvl}"


def list_watchpoints(include_triggered: bool = True) -> list[dict]:
    items = _load()
    if not include_triggered:
        items = [w for w in items if w["status"] == "armed"]
    return sorted(items, key=lambda w: (w["status"] != "armed", -w.get("ts", 0)))


def add(symbol: str, kind: str, level: float, note: str = "",
        side: str | None = None, source: str = "manual",
        confirm: str = "touch") -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    sym = symbol.upper().strip()
    with _lock:
        items = _load()
        for w in items:  # identical armed condition = duplicate, return it
            if (w["status"] == "armed" and w["symbol"] == sym
                    and w["kind"] == kind and abs(w["level"] - level) < 1e-9):
                return w
        wp = {
            "id": uuid.uuid4().hex[:12],
            "symbol": sym,
            "kind": kind,
            "level": float(level),
            "note": (note or "").strip(),
            # buys ring green, sells ring red on the slap
            "side": side if side in ("buy", "sell") else
                    ("buy" if kind in ("price_below", "rsi_below") else "sell"),
            # touch = fire the moment the level trades; close = only fire in
            # the last minutes of the session / after hours, so an intraday
            # wick that recovers doesn't trigger a close-based rule.
            "confirm": confirm if confirm in ("touch", "close") else "touch",
            "source": source,  # manual | advisor
            "status": "armed",
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "ts": time.time(),
        }
        items.append(wp)
        _save(items)
        return wp


def delete(wp_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [w for w in items if w["id"] != wp_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def _met(wp: dict, price: float | None, rsi: float | None) -> bool:
    if wp["kind"] == "price_below":
        return price is not None and price <= wp["level"]
    if wp["kind"] == "price_above":
        return price is not None and price >= wp["level"]
    if wp["kind"] == "rsi_below":
        return rsi is not None and rsi <= wp["level"]
    if wp["kind"] == "rsi_above":
        return rsi is not None and rsi >= wp["level"]
    return False


def already_true(symbol: str, kind: str, level: float,
                 price: float | None, rsi: float | None) -> bool:
    return _met({"kind": kind, "level": level}, price, rsi)


def _in_close_window() -> bool:
    """True in the final minutes of the US session or when the market is
    closed — the window where the current price ~is the closing price."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return True
    mins = et.hour * 60 + et.minute
    return mins >= 15 * 60 + 55 or mins < 9 * 60 + 30


def check(readings: dict[str, tuple[float | None, float | None]],
          close_window: bool | None = None) -> list[dict]:
    """Evaluate armed watchpoints against {SYM: (price, rsi)} readings.

    Triggered watchpoints are marked, journaled, and returned as slap-ready
    signal dicts (rule='watchpoint', zero AI cost). confirm='close'
    watchpoints only evaluate inside the close window."""
    if close_window is None:
        close_window = _in_close_window()
    fired: list[dict] = []
    now = time.time()
    with _lock:
        items = _load()
        for wp in items:
            if wp["status"] != "armed" or wp["symbol"] not in readings:
                continue
            if wp.get("confirm") == "close" and not close_window:
                continue
            price, rsi = readings[wp["symbol"]]
            if not _met(wp, price, rsi):
                continue
            wp["status"] = "triggered"
            wp["triggered_at"] = time.strftime("%Y-%m-%d %H:%M")
            cond = condition_str(wp)
            reading = (f"price ${price:g}" if wp["kind"].startswith("price")
                       else f"RSI {rsi:g}")
            fired.append({
                "id": f"watch:{wp['id']}",
                "symbol": wp["symbol"],
                "side": wp["side"],
                "rule": "watchpoint",
                "label": f"Watchpoint: {cond}",
                "headline": f"{wp['symbol']} hit your watchpoint — {cond}",
                "what": wp["note"] or "Condition met — review the position now.",
                "why": [
                    f"You armed this on {wp['created_at']}: {cond}.",
                    f"Current reading: {reading}.",
                ],
                "target": "",
                "stop": "",
                "price": price or 0.0,
                "held": None,
                "dismissed": False,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "ts": now,
            })
        if fired:
            _save(items)
    for sig in fired:
        try:
            from . import journal
            journal.add_entry(sig["symbol"], "note",
                              f"Watchpoint triggered ({sig['label']}): "
                              f"{sig['what']}", source="auto")
        except Exception as exc:
            print(f"[watchpoints] journal failed: {exc!r}")
    return fired


# ------------------------------------------------------------- AI extraction
_EXTRACT_FMT = (
    'Respond with ONLY a JSON array, no markdown. Each element: '
    '{"symbol": ticker string, "kind": one of "price_below" | "price_above" '
    '| "rsi_below" | "rsi_above", "level": number, "side": "buy" or "sell" '
    '(what the client should do when it fires), "confirm": "close" if the '
    'advice specifies a daily/weekly CLOSE beyond the level, else "touch", '
    '"note": string — the exact action to take, quoted or paraphrased from '
    "the advice, under 25 words}. "
    "Extract ONLY conditions with a concrete numeric level (resolve phrases "
    "like 'this week's low' to the number if it is stated; skip if not). "
    "Skip anything already true at current prices. Empty array if none."
)


def extract_from_advice() -> list[dict]:
    """Mine the latest brief + active strategy for conditional triggers and
    arm them as watchpoints (deduped). One standard-tier call."""
    from . import advisor, strategy

    sources: list[str] = []
    hist = advisor._history.get("portfolio:brief", [])
    if hist:
        h = hist[-1]
        sources.append("Latest brief actions: " + " | ".join(h.get("actions", [])))
        sources.append("Latest brief risks: " + " | ".join(h.get("risks", [])))
    doc = strategy.load()
    if doc and doc.get("approved"):
        sources.append("Strategy playbook: " + " | ".join(doc.get("short_term", [])))
        sources.append("Strategy guardrails: " + " | ".join(doc.get("guardrails", [])))
    if not sources:
        return []

    prompt = ("Extract every actionable watch condition from this investment "
              "advice:\n\n" + "\n".join(sources) + f"\n\n{_EXTRACT_FMT}")
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return []
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        rows = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []

    created: list[dict] = []
    for r in rows if isinstance(rows, list) else []:
        try:
            sym = str(r["symbol"]).upper().strip()
            kind = str(r["kind"])
            level = float(r["level"])
            if not sym or kind not in KINDS or level <= 0:
                continue
            created.append(add(
                sym, kind, level, note=str(r.get("note", "")),
                side=r.get("side"), source="advisor",
                confirm="close" if r.get("confirm") == "close" else "touch"))
        except (KeyError, TypeError, ValueError):
            continue
    return created
