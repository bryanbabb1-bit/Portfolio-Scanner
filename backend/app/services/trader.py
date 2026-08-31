"""The desk's second voice — a trader, because the first one is right about
the wrong thing here.

`advisor._PERSONA` is a growth partner: patience is the strategy, a dip in a
core name is an opportunity, and you never tell the client to sell a
conviction at a loss on a technical break. That is correct for eleven
compounders held for years and fatal for a trade carrying an 18% stop. Asked
to be both at once, one persona hedges a runner ticket into a HOLD — which is
what it did for a month, and why every runner alert read as a warning.

So the sleeve gets its own voice. It never touches the numbers: entry, stop,
target and size are computed by `sleeve.py` from the risk budget BEFORE this
runs, and the note is merged into a ticket that has already been issued and
pushed. A test asserts a note cannot change a level. Its whole job is to say,
in two sentences, what the trade is and what would make it wrong.

It is also strictly optional. No budget, no CLI, bad JSON — it returns None
and the ticket keeps the deterministic reasons the screen wrote. The trade
never waits on the model.
"""
from __future__ import annotations

import json

from ..config import settings

PERSONA = (
    "You are the head of a small proprietary trading desk. You are NOT the "
    "client's financial advisor and you are not managing their long-term "
    "book: a separate sleeve of risk capital funds these trades, every one "
    "carries a hard stop, and the position is sized so a stop-out is a loss "
    "the sleeve absorbs without argument. How you operate:\n"
    "- DECISIVE. The trade is already sized and stopped. Say what it is and "
    "what would make it wrong. Never write 'consider', 'you could', or 'worth "
    "watching' - those are not instructions.\n"
    "- THE EXIT IS NOT NEGOTIABLE. You never argue for widening a stop, "
    "averaging down, or sitting through it. A stopped-out trade is the system "
    "working, not a mistake to be talked out of.\n"
    "- NO THESIS CREEP. The horizon is days. Do not reach for a multi-year "
    "story to justify it and never tell the client to hold it because the "
    "sector is exciting.\n"
    "- SAY WHEN IT IS THIN. If all this name has is one day of volume, say so "
    "plainly. A small position is honest; a confident paragraph about a shell "
    "is not.\n"
    "- NEVER restate the entry, stop, target or size as though you chose "
    "them. They are given. You explain, and you name the risk."
)

_FMT = (
    '\n\nReturn ONLY JSON, no prose around it: '
    '{"headline": "<8 words max: what this trade is>", '
    '"note": "<two sentences: the setup, then the single thing that would '
    'make it wrong>", '
    '"risk": "<one short clause naming the specific risk - a catalyst that '
    'has already happened, a thin float, an earnings date>"}'
)


def note(ticket: dict) -> dict | None:
    """Colour on an already-sized ticket, or None. Costs one budgeted call."""
    if not settings.ADVISOR_ENABLED:
        return None
    from . import advisor, budget
    if not budget.take("signal"):
        return None

    meta = {k: v for k, v in (ticket.get("meta") or {}).items() if v is not None}
    readings = ", ".join(f"{k} {v}" for k, v in meta.items())
    seen = "\n".join(f"- {w}" for w in (ticket.get("why") or []))
    stop_pct = (ticket["stop"] / ticket["entry"] - 1) * 100 if ticket.get("entry") else 0
    prompt = (
        f"{PERSONA}\n\n"
        f"The desk has issued this ticket. It is already sized and stopped:\n"
        f"  {ticket['symbol']} - {ticket['engine']} setup"
        + (f", waiting above {ticket['trigger_above']:.2f}"
           if ticket.get("trigger_above") else "") + "\n"
        f"  buy ${ticket['notional']:,.0f} at {ticket['entry']:.2f}, "
        f"stop {ticket['stop']:.2f} ({stop_pct:.0f}%), "
        f"target {ticket['target']:.2f}\n"
        f"  risking ${ticket['risk_usd']:,.0f} of a "
        f"${ticket['sleeve_equity']:,.0f} sleeve\n"
        f"What the screen saw:\n{seen}\n"
        + (f"Readings: {readings}\n" if readings else "")
        + _FMT
    )
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return None
    a, b = raw.find("{"), raw.rfind("}")
    if a == -1 or b <= a:
        return None
    try:
        obj = json.loads(raw[a:b + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    # Deliberately narrow. Only these three strings are ever taken from the
    # model; a price, a size or a different stop coming back is dropped.
    out = {
        "headline": str(obj.get("headline") or "").strip()[:80],
        "note": str(obj.get("note") or "").strip()[:400],
        "risk": str(obj.get("risk") or "").strip()[:160],
        "engine": "claude",
    }
    return out if out["note"] else None


def enrich(ticket_id: str) -> dict | None:
    """Write a note onto a stored ticket. Runs in the background off the
    heartbeat, so it re-reads the ticket under the sleeve's lock and merges
    rather than assuming the ticket is still as it was."""
    from . import sleeve
    with sleeve._lock:
        book = sleeve.load()
        t = sleeve.get(ticket_id, book)
        if not t or t.get("status") not in ("armed", "watching") or t.get("note"):
            return None
        snapshot = dict(t)

    written = note(snapshot)
    if not written:
        return None

    with sleeve._lock:
        book = sleeve.load()
        t = sleeve.get(ticket_id, book)
        if not t or t.get("note"):
            return None
        t["note"] = written["note"]
        t["note_risk"] = written["risk"]
        t["note_engine"] = written["engine"]
        if written["headline"]:
            t["headline"] = written["headline"]
        sleeve.save(book)
    return written
