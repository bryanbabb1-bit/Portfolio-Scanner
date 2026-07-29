"""Durable record of the client's conversation with the advisor.

The claude CLI holds a session per context key, so a follow-up can `--resume`
with the brief and data still in context. But that session was the ONLY place
the conversation lived. A backend restart, a reboot, or an expired session id
dropped the whole thread — the advisor then answered the next question as if
you had never spoken — and a thread started on the phone was invisible on the
desktop, because the turns only existed in that browser's localStorage.

This persists the turns themselves. Two things follow:

  * any device can load the same conversation (`recent`), and
  * a lost session degrades to a compact recap (`recap_block`) instead of
    amnesia — he still knows what you discussed and what he told you.

The recap is deliberately small. It is not a transcript replay; it is the
minimum that keeps him from contradicting himself or asking you something you
already answered.
"""
from __future__ import annotations

import json
import time
from threading import Lock

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "advisor_chat.json"

# Enough to scroll a working history per context; bounded so the file can't grow
# without limit on a machine that stays up for weeks.
KEEP_TURNS = 60
# How many turns feed the recap. Past ~6 the prompt cost stops buying accuracy.
RECAP_TURNS = 6

_lock = Lock()


def key_for(kind: str, symbol: str | None) -> str:
    """The context key. Shared with the advisor's session + history maps so the
    conversation, the resumable session and the prior-advice block can never
    drift onto different keys."""
    if kind == "portfolio":
        return "portfolio:brief"
    if kind == "strategy":
        return "strategy:plan"
    return f"{kind}:{(symbol or '').upper()}"


def _load() -> dict[str, list[dict]]:
    # UTF-8 first, cp1252 fallback: the briefs already learned that reading a
    # UTF-8 file with the Windows default codec mangles em-dashes.
    for enc in ("utf-8", "cp1252"):
        try:
            with open(_FILE, encoding=enc) as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return {}


def _save(data: dict[str, list[dict]]) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        # Losing the log must never cost the client their answer.
        print(f"[chat] could not persist conversation: {exc!r}")


def record(key: str, question: str, answer: str, points: list[str] | None = None) -> None:
    """Append one completed turn."""
    turn = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "q": (question or "").strip(),
        "a": (answer or "").strip(),
        "points": list(points or []),
    }
    with _lock:
        data = _load()
        data[key] = (data.get(key) or [])[-(KEEP_TURNS - 1):] + [turn]
        _save(data)


def recent(key: str, limit: int = KEEP_TURNS) -> list[dict]:
    """Oldest-first turns for this context, newest `limit` of them."""
    with _lock:
        return (_load().get(key) or [])[-limit:]


def clear(key: str) -> int:
    """Forget this conversation. Returns how many turns were dropped."""
    with _lock:
        data = _load()
        dropped = len(data.pop(key, []) or [])
        _save(data)
    return dropped


def recap_block(key: str, turns: int = RECAP_TURNS) -> str:
    """Prompt text that re-establishes the thread when the session is gone.

    Only used on the cold path — when there is a live session to resume, the
    model already holds all of this and re-sending it would just cost tokens.
    """
    history = recent(key, turns)
    if not history:
        return ""
    lines: list[str] = []
    for t in history:
        q = t.get("q", "")[:220]
        a = t.get("a", "")[:260]
        lines.append(f"[{t.get('ts', '')}] Client asked: {q}")
        lines.append(f"  You answered: {a}")
    return (
        "\nYOUR ONGOING CONVERSATION WITH THIS CLIENT — you are the same advisor "
        "and this thread is continuous. You do NOT have the live session any "
        "more (the machine restarted), so this is your record of it:\n"
        + "\n".join(lines)
        + "\nPick the thread back up as if you remembered it. Do not "
        "reintroduce yourself, do not re-explain things you already covered, "
        "and do not ask the client for anything they already told you here. "
        "If you now disagree with something you said above, say so explicitly "
        "and give the reason.\n"
    )
