"""Learning loop — close the cycle: Research -> Trade -> Review -> Optimize.

Two records of every rule already exist and never spoke to each other:

  scorecard.compute()  what the rule did LIVE, graded against today's price.
                       Small sample, but it is the app's actual record.
  backtest.run()       what the rule did over five years of history.
                       Large sample, but it is a replay, not a track record.

This joins them into one health table per rule and rules on each: EARNING,
MARGINAL, RETUNE or RETIRE. That verdict then feeds back two ways — into the
advisor's facts, so it knows which of its own screens have been working, and
into a proposals file the client can accept.

Proposals are NEVER auto-applied. Two reasons, both deliberate:

  1. Tuning thresholds against the same history you measured on is
     curve-fitting. The honest version re-tests at the new setting, which is a
     parameter sweep this does not do — so a proposal is explicitly labelled
     unvalidated.
  2. Silently changing what fires a slap at the client, based on ~50 live
     signals, is not learning. It is drift.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings
from . import backtest as bt
from . import scorecard

_FILE = settings.PORTFOLIO_FILE.parent / "rule_tuning.json"
_lock = threading.Lock()

# A live sample smaller than this is reported but never drives a verdict.
MIN_LIVE = 5
# Backtest sample below this is too thin to retire a rule on.
MIN_BACKTEST = 20

VERDICTS = ("EARNING", "MARGINAL", "RETUNE", "RETIRE")

# What could actually be changed per rule, in plain words. Used to describe a
# proposal — never to compute one.
_KNOBS = {
    "oversold-at-support": "the RSI ceiling (35) and how close to the 200-day it must be (5%)",
    "quality-dip": "the RSI ceiling (38) and the required composite score (45)",
    "washed-out-reversal": "the RSI ceiling (30), bounce size (2%) and volume multiple (1.5x)",
    "rsi-buy-zone": "the RSI ceiling (32) and the required composite score (35)",
    "rsi-reclaim": "the reclaim level (45) and how washed out it must have been (35)",
    "breakout-triggering": "the score bar (72), distance from highs (5%) and volume (1.3x)",
    "high-conviction-discovery": "the discovery score bar (72)",
    "momentum-ignition": "the 5-day move (12%) and volume multiple (1.5x)",
    "blowoff-top": "the RSI floor (80) and volume multiple (2x)",
    "rsi-sell-zone": "the RSI floor (75) and the volume/at-highs confirmation",
    "trend-break": "the day-change trigger (-3%) and the death-cross condition",
    "sharp-breakdown": "the day-change trigger (-8%) and volume multiple (1.5x)",
}


def _load() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _save(d: dict) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[learning] persist failed: {exc!r}")


def _verdict(bt_row: dict | None, live: dict | None) -> tuple[str, str]:
    """Rule on a rule. Returns (verdict, one-line reason).

    The backtest carries the verdict because it is the larger sample; live
    results confirm or contradict it. A rule with no backtest evidence is
    UNTESTED-marginal, never retired on a handful of live fires.
    """
    if not bt_row or bt_row["signals"] < MIN_BACKTEST:
        n = bt_row["signals"] if bt_row else 0
        return "MARGINAL", (
            f"Only {n} historical signals — too thin to rule on. "
            f"Needs {MIN_BACKTEST}."
        )

    pf = bt_row.get("profit_factor")
    avg = bt_row["avg_20"]
    n = bt_row["signals"]

    # No losses at all in a large sample: real, and good.
    if pf is None:
        return ("EARNING", f"{n} signals, no losing trades at 20 sessions.") if avg > 0 \
            else ("MARGINAL", f"{n} signals but no measurable edge.")

    live_note = ""
    if live and live["signals"] >= MIN_LIVE:
        agree = (live["avg_effective_pct"] > 0) == (avg > 0)
        live_note = (
            f" Live agrees ({live['signals']} fired, "
            f"{live['avg_effective_pct']:+.1f}%)."
            if agree else
            f" Live DISAGREES ({live['signals']} fired, "
            f"{live['avg_effective_pct']:+.1f}%) — treat with caution."
        )

    if pf >= 1.3 and avg > 0:
        return "EARNING", f"{n} signals, {avg:+.2f}% average, profit factor {pf}.{live_note}"
    if pf >= 1.0:
        return "MARGINAL", f"{n} signals, profit factor {pf} — barely pays for itself.{live_note}"
    if pf >= 0.7:
        return "RETUNE", f"{n} signals, profit factor {pf}, {avg:+.2f}% average — loses money as set.{live_note}"
    return "RETIRE", f"{n} signals, profit factor {pf}, {avg:+.2f}% average — actively harmful.{live_note}"


def rule_health() -> dict:
    """The joined table. Uses the LAST backtest; never triggers a new replay."""
    report = bt.last_result()
    live = scorecard.compute()

    bt_rules = {r["rule"]: r for r in (report or {}).get("rules", [])}
    live_rules = {r["rule"]: r for r in live.get("rules", [])}
    accepted = _load()

    rows = []
    for rule in sorted(set(bt_rules) | set(live_rules)):
        b = bt_rules.get(rule)
        l = live_rules.get(rule)
        verdict, reason = _verdict(b, l)
        rows.append({
            "rule": rule,
            "side": (b or l or {}).get("side", "buy"),
            "verdict": verdict,
            "reason": reason,
            "backtest_signals": (b or {}).get("signals", 0),
            "backtest_win_rate": (b or {}).get("win_rate"),
            "backtest_avg_pct": (b or {}).get("avg_20"),
            "profit_factor": (b or {}).get("profit_factor"),
            "live_signals": (l or {}).get("signals", 0),
            "live_win_rate": (l or {}).get("win_rate"),
            "live_avg_pct": (l or {}).get("avg_effective_pct"),
            "knob": _KNOBS.get(rule),
            "proposal": _proposal(rule, verdict),
            "accepted": accepted.get(rule),
        })

    order = {v: i for i, v in enumerate(("RETIRE", "RETUNE", "MARGINAL", "EARNING"))}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -(r["backtest_signals"] or 0)))

    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    return {
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rules": rows,
        "counts": counts,
        "backtest_as_of": (report or {}).get("as_of"),
        "backtest_period": (report or {}).get("period"),
        "live_signals_graded": live.get("count", 0),
        "live_win_rate": live.get("overall_win_rate"),
        "has_backtest": bool(report),
        "notes": _notes(report, live, counts),
    }


def _proposal(rule: str, verdict: str) -> str | None:
    """Plain-English next step. Deliberately NOT a computed threshold."""
    if verdict == "EARNING":
        return None
    if verdict == "MARGINAL":
        return "Leave as is and keep watching — no evidence to act on yet."
    knob = _KNOBS.get(rule, "its thresholds")
    if verdict == "RETUNE":
        return (
            f"Raise the bar on {knob} so it fires less often, then re-run the "
            f"replay to check the change actually helped. Not yet validated."
        )
    return (
        f"Stop firing this rule, or raise {knob} far enough that it becomes a "
        f"different rule. Re-run the replay before trusting any new setting. "
        f"Not yet validated."
    )


def _notes(report, live, counts) -> list[str]:
    notes = []
    if not report:
        notes.append(
            "No backtest on record — run the replay on the Backtest sheet, "
            "or every verdict here is based on live signals alone."
        )
    if live.get("count", 0) < MIN_LIVE:
        notes.append(
            f"Only {live.get('count', 0)} live signals graded so far; live "
            f"columns are informational until there are {MIN_LIVE}."
        )
    if counts.get("RETIRE"):
        notes.append(
            f"{counts['RETIRE']} rule(s) lose money as configured. Proposals "
            "are suggestions only — nothing here changes what fires until you "
            "accept it."
        )
    notes.append(
        "Verdicts come from the replay, which is long-only and "
        "survivorship-biased. A rule can look bad because the regime favoured "
        "holding, not because the logic is wrong."
    )
    return notes


def accept(rule: str, note: str = "") -> dict:
    """Record that the client accepted a proposal. Records intent, not a change.

    Applying it means editing conviction._detect, which is a code change on
    purpose — thresholds that fire real alerts should move in a reviewed diff,
    not silently from a button."""
    with _lock:
        d = _load()
        d[rule] = {
            "rule": rule,
            "accepted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": str(note or "")[:400],
        }
        _save(d)
        return d[rule]


def unaccept(rule: str) -> bool:
    with _lock:
        d = _load()
        existed = d.pop(rule, None) is not None
        _save(d)
        return existed


def facts_block() -> str:
    """Rule health for advisor prompts — so it knows which screens have worked."""
    try:
        h = rule_health()
    except Exception:
        return ""
    if not h["has_backtest"]:
        return ""
    earning = [r["rule"] for r in h["rules"] if r["verdict"] == "EARNING"]
    weak = [r for r in h["rules"] if r["verdict"] in ("RETUNE", "RETIRE")]
    if not earning and not weak:
        return ""
    lines = ["RULE TRACK RECORD (from replaying these screens over history):"]
    if earning:
        lines.append(f"- Screens that have EARNED their bar: {', '.join(earning)}.")
    for r in weak:
        lines.append(
            f"- {r['rule']} has NOT worked ({r['backtest_avg_pct']:+.2f}% average "
            f"over {r['backtest_signals']} signals) — weight it lightly and say "
            f"so if you lean on it."
        )
    return "\n".join(lines)
