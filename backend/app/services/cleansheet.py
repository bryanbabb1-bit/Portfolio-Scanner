"""Clean Sheet — the book the desk would build from scratch, then the diff.

The question this exists to answer: is the advisor recommending your holdings
because it believes in them, or because they are what it was shown? Those look
identical from the outside, and no amount of asking the advisor resolves it —
it will rationalise whatever it is anchored to.

So the construction step is run BLIND. The prompt gets the goal, the horizon,
the contribution, the risk appetite and a live market-wide candidate list. It
does NOT get the current holdings, the current allocation, the standing calls,
the journal, or the strategy doc. There is a test asserting exactly that,
because the moment holdings leak into this prompt the whole exercise becomes
theatre.

The diff is then computed in Python, not by the model. Overlap is a fact about
two lists; asking a model to grade its own agreement with the client would
reintroduce the bias by the back door.

Reading the result:
  HIGH overlap  -> your book really is what a from-scratch build looks like.
                   The concentration is a conviction, not an artifact.
  LOW overlap   -> the desk, unanchored, builds something materially different.
                   That gap is the thing to think about.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings
from . import advisor, discovery
from . import portfolio as pf_service

_FILE = settings.PORTFOLIO_FILE.parent / "cleansheet.json"
_lock = threading.Lock()
CACHE_TTL = 24 * 3600          # a from-scratch view does not change hourly

# Candidates fed to the blind build, per theme. Enough to be a real menu
# without letting one sleeve dominate by sheer count.
PER_THEME = 6


_SCHEMA = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
    '"thesis" (string: the strategy behind this portfolio in 1-2 sentences), '
    '"allocation" (array of 4-9 objects {"theme": string, "pct": number, '
    '"why": string} — theme must come from the list given, pct are percents '
    'summing to about 100, why is one sentence), '
    '"picks" (array of 8-15 objects {"symbol": string, "theme": string, '
    '"pct": number, "why": string} — the actual names, pct summing to about '
    '100 and consistent with the allocation, why is one short sentence naming '
    'the specific reason to own it), '
    '"avoided" (array of 1-3 strings: sectors or styles you deliberately gave '
    'little or no weight, and why). '
    'Every string is one self-contained sentence under 28 words.'
)


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
        print(f"[cleansheet] persist failed: {exc!r}")


def last_result(max_age: int | None = None) -> dict | None:
    d = _load()
    if not d:
        return None
    if max_age is not None and time.time() - float(d.get("ts", 0)) > max_age:
        return None
    return d


# ------------------------------------------------------------- the blind build
def _candidate_block() -> str:
    """A market-wide, live-scored menu. Owned names included and UNMARKED."""
    res = discovery.discover(min_score=0, limit=1000, include_owned=True)
    by_theme: dict[str, list] = {}
    for c in res["results"]:
        by_theme.setdefault(c.theme, []).append(c)

    lines = []
    for theme in discovery.all_themes():
        rows = by_theme.get(theme, [])[:PER_THEME]
        if not rows:
            continue
        lines.append(f"{theme}: " + "; ".join(
            f"{c.symbol} (setup {c.score:.0f}/100, ${c.price})" for c in rows
        ))
    return "\n".join(lines)


def _goal_block(goals: dict) -> str:
    parts = []
    if goals.get("target_value"):
        parts.append(f"Target portfolio value: ${float(goals['target_value']):,.0f}")
    if goals.get("horizon"):
        parts.append(f"Horizon: {goals['horizon']}")
    if goals.get("monthly_contribution"):
        parts.append(
            f"Monthly contribution: ${float(goals['monthly_contribution']):,.0f}")
    if goals.get("risk_appetite"):
        parts.append(f"Risk appetite: {goals['risk_appetite']}")
    if goals.get("notes"):
        parts.append(f"Client notes: {goals['notes']}")
    return "\n".join(parts) or "No stated goal — assume long-term growth."


def build_prompt(goals: dict, equity: float) -> str:
    """The blind construction prompt. Deliberately contains NO holdings."""
    return (
        f"{advisor._PERSONA}\n\n"
        f"Build a portfolio from a BLANK SHEET.\n\n"
        f"You are constructing a book for a new client with ${equity:,.0f} to "
        f"invest. You have NOT been told what they currently own, and you must "
        f"not guess or assume — build purely from the goal and the market.\n\n"
        f"THE GOAL:\n{_goal_block(goals)}\n\n"
        f"AVAILABLE THEMES (use these exact names):\n"
        + "\n".join(f"- {k}: {v}" for k, v in discovery.theme_menu().items())
        + f"\n\nLIVE CANDIDATES (setup score is momentum/breakout readiness "
        f"only — it is NOT a quality or valuation judgement, so do not rank on "
        f"it alone; you may also use names not listed):\n{_candidate_block()}\n\n"
        f"Build the book YOU believe in for this goal. Concentrate where you "
        f"have real conviction and leave out what you do not — this is not a "
        f"diversification exercise and an index-hugging answer is a failure. "
        f"But it is also not a momentum chase: weigh business quality and the "
        f"horizon. Be specific and take positions.\n\n"
        f"{_SCHEMA}"
    )


# ------------------------------------------------------------------- the diff
def _current_allocation() -> tuple[dict[str, float], dict[str, float], float]:
    """(theme -> pct, symbol -> pct, equity) for the real book."""
    summary, held = pf_service.portfolio_summary()
    equity = summary.total_market_value or 0.0
    if equity <= 0:
        return {}, {}, 0.0
    by_theme: dict[str, float] = {}
    for theme, val in (summary.by_theme or {}).items():
        by_theme[theme] = round(val / equity * 100, 1)
    if summary.cash:
        by_theme["Cash & Income"] = round(
            by_theme.get("Cash & Income", 0) + summary.cash / equity * 100, 1)
    by_symbol = {
        r.symbol: round((r.market_value or 0) / equity * 100, 1)
        for r in held if (r.market_value or 0) > 0
    }
    return by_theme, by_symbol, equity


def _diff(target_alloc: list[dict], picks: list[dict]) -> dict:
    current_theme, current_sym, equity = _current_allocation()

    tgt = {str(a.get("theme")): float(a.get("pct") or 0) for a in target_alloc}
    themes = sorted(set(tgt) | set(current_theme),
                    key=lambda t: -(tgt.get(t, 0) + current_theme.get(t, 0)))
    rows = [{
        "theme": t,
        "target_pct": round(tgt.get(t, 0.0), 1),
        "current_pct": round(current_theme.get(t, 0.0), 1),
        "delta": round(tgt.get(t, 0.0) - current_theme.get(t, 0.0), 1),
    } for t in themes]

    held = set(current_sym)
    pick_syms = [str(p.get("symbol", "")).upper() for p in picks]
    kept = [s for s in pick_syms if s in held]
    fresh = [s for s in pick_syms if s and s not in held]

    # Overlap by WEIGHT, not by name count: agreeing on a 1% position is not
    # the same as agreeing on a 16% one.
    total_w = sum(float(p.get("pct") or 0) for p in picks) or 1.0
    kept_w = sum(float(p.get("pct") or 0) for p in picks
                 if str(p.get("symbol", "")).upper() in held)

    blind_spots = [r for r in rows if r["target_pct"] >= 5 and r["current_pct"] == 0]
    overweight = [r for r in rows if r["delta"] <= -10]

    return {
        "themes": rows,
        "held_picks": kept,
        "new_picks": fresh,
        "overlap_pct": round(kept_w / total_w * 100, 0),
        "name_overlap_pct": round(100 * len(kept) / len(pick_syms), 0) if pick_syms else 0,
        "blind_spots": blind_spots,
        "overweight": overweight,
        "equity": round(equity, 2),
    }


def _verdict(diff: dict) -> tuple[str, str]:
    o = diff["overlap_pct"]
    spots = len(diff["blind_spots"])
    if o >= 60:
        return "ALIGNED", (
            f"{o:.0f}% of the from-scratch book is names you already own. Your "
            "concentration is a conviction the desk shares, not an artifact of "
            "what it was shown."
        )
    if o >= 30:
        return "PARTIAL", (
            f"{o:.0f}% overlap. The core holds up, but built blind the desk "
            f"allocates meaningfully differently"
            + (f" and wants {spots} sleeve(s) you have nothing in." if spots else ".")
        )
    return "DIVERGENT", (
        f"Only {o:.0f}% of the from-scratch book is what you own. Unanchored, "
        "the desk builds something materially different — that gap is the "
        "thing worth thinking about."
    )


# ------------------------------------------------------------------------ run
def build(force: bool = False) -> dict:
    if not force:
        cached = last_result(CACHE_TTL)
        if cached:
            return cached

    summary, _held = pf_service.portfolio_summary()
    equity = summary.total_market_value or 10_000.0

    goals = {}
    try:
        from . import strategy
        goals = (strategy.load() or {}).get("goals") or {}
    except Exception:
        goals = {}

    if not settings.ADVISOR_ENABLED:
        return {"ts": time.time(), "engine": "disabled", "error":
                "Advisor is disabled — cannot build a clean sheet.",
                "allocation": [], "picks": [], "diff": None}

    prompt = build_prompt(goals, equity)
    raw, _ = advisor._run_claude(prompt)      # default = best model
    if not raw:
        return {"ts": time.time(), "engine": "unavailable", "error":
                "The desk could not be reached — try again.",
                "allocation": [], "picks": [], "diff": None}

    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        obj = json.loads(text[start : end + 1]) if start != -1 and end > start else {}
    except json.JSONDecodeError:
        obj = {}

    allocation = [
        {"theme": str(a.get("theme", "")), "pct": float(a.get("pct") or 0),
         "why": str(a.get("why", ""))}
        for a in (obj.get("allocation") or [])
        if isinstance(a, dict) and a.get("theme")
    ]
    picks = [
        {"symbol": str(p.get("symbol", "")).upper(),
         "theme": str(p.get("theme", "")), "pct": float(p.get("pct") or 0),
         "why": str(p.get("why", ""))}
        for p in (obj.get("picks") or [])
        if isinstance(p, dict) and p.get("symbol")
    ]

    diff = _diff(allocation, picks)
    verdict, headline = _verdict(diff)

    result = {
        "ts": time.time(),
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "claude",
        "goals": goals,
        "equity": diff["equity"],
        "thesis": str(obj.get("thesis", "")),
        "allocation": allocation,
        "picks": picks,
        "avoided": advisor._as_bullets(obj.get("avoided")),
        "diff": diff,
        "verdict": verdict,
        "headline": headline,
        "error": None,
        "method": (
            "Built blind: the prompt contained the goal, the horizon and a "
            "market-wide candidate list, but NOT the current holdings, "
            "allocation, standing calls or strategy. The comparison below is "
            "computed in code, not by the model."
        ),
    }
    with _lock:
        _save(result)
    return result
