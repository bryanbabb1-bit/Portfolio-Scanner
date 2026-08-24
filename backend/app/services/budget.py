"""A hard daily ceiling on Claude CLI calls, with the things you read reserved.

WHY
---
On 2026-08-24 the advisor stopped answering. Nothing was broken: the account
had run out of subscription quota, so `claude -p` exited immediately on every
model. The cause was traceable to a single line changed four days earlier —
`signals_owned_only` was flipped off so the watchdog would look at the whole
market instead of the 24 names in the book.

Signals per day, before and after that flip:

    2026-08-10     1
    2026-08-19     1
    2026-08-20    29      <- the flip
    2026-08-21    11
    2026-08-24    21

Every new signal costs a CLI call to enrich, and a slap costs another to turn
into a recommendation. Add the overnight desk at six calls per debate and the
subscription ran dry before lunch.

The flip itself was right and stays — Bryan asked to see the whole market and
cash is not a gate on knowing. What was missing is that nothing in the app had
any idea what it was spending, so an uncapped background loop could quietly
consume the quota that his own questions needed.

HOW
---
Four tiers, each with its own daily allowance:

    user    the questions he actually asks       NEVER blocked
    brief   morning brief and close recap        reserved, small
    desk    overnight debates                    capped
    signal  whole-market enrichment              capped hardest

The ordering is deliberate. When the budget runs low the app degrades by
dropping the AI commentary on a mover — the mover is still shown, still pushed,
still has its headline — rather than by failing to answer a direct question.
Losing the write-up costs a sentence. Losing the answer costs the feature.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "cli_budget.json"

# Calls per calendar day, ET. A debate is six calls, a brief is one or two, an
# enriched signal is one. These are sized so a normal day spends well under the
# subscription's ceiling and leaves room for a busy tape.
LIMITS: dict[str, int] = {
    "user": 0,        # 0 = unlimited; his own questions are never rationed
    "brief": 12,      # morning + close, with retries for a CLI hiccup
    "desk": 36,       # six debates
    "signal": 24,     # the tier that blew the quota
}


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def _read() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("date") == _today():
            return d
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return {"date": _today(), "spent": {}}


def _write(d: dict) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except OSError as exc:
        print(f"[budget] persist failed: {exc!r}")


def remaining(tier: str) -> int | None:
    """Calls left in `tier` today. None means unlimited."""
    cap = LIMITS.get(tier, 0)
    if not cap:
        return None
    return max(0, cap - int(_read().get("spent", {}).get(tier, 0)))


def take(tier: str, n: int = 1) -> bool:
    """Claim `n` calls for `tier`. False when the tier is spent for the day.

    Callers must treat False as "do the cheap thing", never as an error: the
    signal still fires, the mover is still pushed, it simply arrives without a
    model-written paragraph attached.
    """
    cap = LIMITS.get(tier, 0)
    d = _read()
    spent = d.setdefault("spent", {})
    used = int(spent.get(tier, 0))
    if cap and used + n > cap:
        if not spent.get(f"{tier}_blocked"):
            print(f"[budget] {tier} exhausted for {d['date']} "
                  f"({used}/{cap}) — degrading to no-AI for the rest of the day")
        spent[f"{tier}_blocked"] = int(spent.get(f"{tier}_blocked", 0)) + 1
        _write(d)
        return False
    spent[tier] = used + n
    _write(d)
    return True


def state() -> dict:
    """Today's spend, for the dashboard and for answering 'why is it quiet'."""
    d = _read()
    spent = d.get("spent", {})
    return {
        "date": d.get("date"),
        "limits": dict(LIMITS),
        "spent": {k: int(v) for k, v in spent.items() if not k.endswith("_blocked")},
        "blocked": {k[:-8]: int(v) for k, v in spent.items() if k.endswith("_blocked")},
        "remaining": {k: remaining(k) for k in LIMITS},
        "ts": time.time(),
    }
