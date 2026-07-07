"""Strategy mode — a persistent two-horizon growth plan for the portfolio.

The strategy document is co-created: the client sets goals (target value,
horizon, contributions, risk appetite), the advisor drafts a structured plan
(short-term playbook, long-term strategy, allocation targets, guardrails,
milestones), and the client iterates via chat then approves. Once approved,
the plan is injected into every brief so daily tactical advice aligns with —
and measures progress against — the agreed strategy.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "strategy.json"
_lock = threading.Lock()


def load() -> dict | None:
    try:
        with open(_FILE) as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(doc: dict) -> dict:
    doc = dict(doc)
    doc["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w") as f:
            json.dump(doc, f, indent=2)
    return doc


def facts_block() -> str:
    """The approved strategy formatted for advisor prompts ('' when none)."""
    doc = load()
    if not doc or not doc.get("approved"):
        return ""
    g = doc.get("goals", {})
    lines = ["THE CLIENT'S AGREED STRATEGY (align all advice to this plan and "
             "measure progress against it; flag and justify any deviation):"]
    goal_bits = []
    if g.get("target_value"):
        goal_bits.append(f"grow to ${g['target_value']:,.0f}")
    if g.get("horizon"):
        goal_bits.append(f"horizon {g['horizon']}")
    if g.get("monthly_contribution"):
        goal_bits.append(f"${g['monthly_contribution']:,.0f}/mo new capital")
    if g.get("risk_appetite"):
        goal_bits.append(f"{g['risk_appetite']} risk appetite")
    if goal_bits:
        lines.append("  Goals: " + ", ".join(goal_bits))
    if doc.get("thesis"):
        lines.append(f"  Thesis: {doc['thesis']}")
    targets = doc.get("allocation_targets") or {}
    if targets:
        lines.append("  Allocation targets: " + ", ".join(
            f"{k} {v:g}%" for k, v in targets.items()))
    for label, key in (("Short-term playbook", "short_term"),
                       ("Long-term strategy", "long_term"),
                       ("Guardrails", "guardrails")):
        items = doc.get(key) or []
        if items:
            lines.append(f"  {label}:")
            lines.extend(f"    - {x}" for x in items[:6])
    return "\n".join(lines)


def generate(inputs: dict, deep: bool = False) -> dict:
    """Draft a strategy with the best model, grounded in the full book."""
    from . import advisor, discovery, insights, journal
    from . import portfolio as pf_service

    summary, reports = pf_service.portfolio_summary()
    risk = insights.compute_risk(reports)
    alerts = insights.build_alerts(reports)
    try:
        candidates = discovery.discover(min_score=0, limit=8)["results"]
    except Exception:
        candidates = None
    facts = advisor._facts_from_portfolio(summary, reports, risk, alerts,
                                          candidates)

    g_lines = []
    if inputs.get("target_value"):
        g_lines.append(f"Target portfolio value: ${inputs['target_value']:,.0f}")
    if inputs.get("horizon"):
        g_lines.append(f"Time horizon: {inputs['horizon']}")
    if inputs.get("monthly_contribution") is not None:
        g_lines.append(f"New capital available: "
                       f"${inputs['monthly_contribution']:,.0f}/month")
    if inputs.get("risk_appetite"):
        g_lines.append(f"Risk appetite: {inputs['risk_appetite']}")
    if inputs.get("notes"):
        g_lines.append(f"Client notes: {inputs['notes']}")
    goals = "\n".join(g_lines) or "No explicit goals given — infer sensible ones."

    prior = load()
    # If a strategy chat is in progress, RESUME it so the revision incorporates
    # everything discussed there — that conversation is the whole point of
    # 'iterate then revise'. Falls back to a fresh draft when there's no chat.
    prior_sid = advisor._sessions.get("strategy:plan") if prior else None
    prior_block = ""
    if prior and prior.get("thesis"):
        prior_block = (
            f"\nThe current ACTIVE strategy you are REVISING:\n"
            f"Thesis: {prior['thesis']}\n"
            f"Guardrails: {' | '.join(prior.get('guardrails', []))}\n"
            f"Allocation targets: {prior.get('allocation_targets', {})}\n"
            f"Incorporate everything discussed in our conversation into this "
            f"revision; keep what still holds, change what we agreed to change.\n")

    prompt = (
        f"{advisor._PERSONA}\n\n"
        f"{advisor._RESEARCH_PREFIX if deep else ''}"
        f"Design a portfolio GROWTH STRATEGY for this client, spanning a "
        f"short-term horizon (next 4-12 weeks) and a long-term horizon "
        f"(1+ years).\n\nThe client's goals:\n{goals}\n\n"
        f"The book today:\n\n{facts}\n{prior_block}\n"
        f"Ground every number in the data above. The strategy must be "
        f"executable by a self-directed retail investor making a few trades "
        f"per week. Respond with ONLY a JSON object, no markdown: "
        f'{{"thesis": string (the strategy in 1-2 sentences), '
        f'"short_term": array of 4-6 strings (the 4-12 week playbook — one '
        f'concrete move/rule per bullet with tickers and levels), '
        f'"long_term": array of 4-6 strings (the 1+ year strategy — core '
        f'positions, compounding plan, what to build toward), '
        f'"allocation_targets": object mapping theme names to target percent '
        f'(use these themes: {", ".join(_theme_names())}; include Cash & '
        f'Income; numbers must sum to about 100), '
        f'"guardrails": array of 3-5 strings (hard risk rules — position '
        f'caps, drawdown responses, when to go to cash), '
        f'"milestones": array of 3-5 strings (checkpoints with a value or '
        f'condition and rough date to know the plan is on track)}}. '
        f"Every bullet a single self-contained sentence under 28 words."
    )
    raw, sid = advisor._run_claude(prompt, resume=prior_sid, research=deep)
    if not raw:
        raise RuntimeError("The advisor did not respond — try again.")
    start, end = raw.find("{"), raw.rfind("}")
    obj = json.loads(raw[start : end + 1])

    doc = {
        "goals": {k: inputs.get(k) for k in
                  ("target_value", "horizon", "monthly_contribution",
                   "risk_appetite", "notes")},
        "thesis": str(obj.get("thesis", "")),
        "short_term": advisor._as_bullets(obj.get("short_term")),
        "long_term": advisor._as_bullets(obj.get("long_term")),
        "allocation_targets": {
            str(k): float(v) for k, v in
            (obj.get("allocation_targets") or {}).items()
            if isinstance(v, (int, float))
        },
        "guardrails": advisor._as_bullets(obj.get("guardrails")),
        "milestones": advisor._as_bullets(obj.get("milestones")),
        "approved": False,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "claude",
    }
    if sid:
        advisor._remember_session("strategy:plan", sid)
    return save(doc)


def _theme_names() -> list[str]:
    from . import portfolio as pf_service
    try:
        return list(pf_service.load_portfolio().get("themes", {}).keys())
    except Exception:
        return ["AI", "AI Infrastructure", "Compute Power", "Energy", "Tech",
                "Cash & Income"]
