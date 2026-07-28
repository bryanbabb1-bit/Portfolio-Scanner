"""Agent debate — five specialists argue a ticker, then a judge rules.

Until now one persona spoke once (`advisor._PERSONA`). A single voice has a
single blind spot: whatever the persona is disposed to see, it sees every
time. This runs five *adversarially* briefed agents over the same facts and
scores the disagreement, so a thesis has to survive its strongest objection
before it reaches the client.

    ROUND 1  BULL / BEAR / MACRO      opening arguments, concurrent
    ROUND 2  RISK / EXECUTION         see round 1, then respond
    JUDGE                             scores it, returns APPROVE or REJECT

Cost discipline (this app runs 24/7 on a Claude subscription, not an API):
a debate is SIX CLI calls, so it is strictly on-demand — never on a poll,
never on a page load. The five agents run the standard model; only the judge
uses the default (best) model. Results cache for 6h per symbol.

The debate decides WHETHER. It never decides HOW MUCH — position size comes
from `risk.plan_for`, which is deterministic. A model that both argues for a
trade and sizes it is marking its own homework.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from . import advisor, journal, risk as risk_service, stance as stance_service
from . import portfolio as pf_service

_FILE = settings.PORTFOLIO_FILE.parent / "debates.json"
_lock = threading.Lock()
CACHE_TTL = 6 * 3600

_VALID_ACTIONS = {"BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID", "WATCH"}


# ------------------------------------------------------------------ personas
# Each agent is briefed to ARGUE ITS CORNER, not to be balanced. Balance is
# the judge's job; five balanced agents would just agree five times.
AGENTS = [
    {
        "key": "bull",
        "name": "Bull Agent",
        "round": 1,
        "brief": (
            "You are the BULL. Build the strongest honest case FOR owning this "
            "name. Find the upside, the catalysts, what the market is "
            "under-appreciating, and what the business could look like in 2-3 "
            "years. Argue your corner hard — the Bear is arguing the other side "
            "and a judge will weigh you both. Do not hedge or present the "
            "downside; that is not your job here. But never invent a fact."
        ),
    },
    {
        "key": "bear",
        "name": "Bear Agent",
        "round": 1,
        "brief": (
            "You are the BEAR. Build the strongest honest case AGAINST this "
            "name right now. What breaks the thesis? Where is the multiple "
            "wrong, the competition real, the cycle turning, the balance sheet "
            "thin? What is the specific scenario in which the client loses "
            "money here? Argue your corner hard and do not hedge. Never invent "
            "a fact — if the data does not support a worry, say the honest "
            "worry that it does support."
        ),
    },
    {
        "key": "macro",
        "name": "Macro Agent",
        "round": 1,
        "brief": (
            "You are MACRO. Ignore the company story. Judge this position on "
            "the top-down picture only: rates and liquidity, the sector's place "
            "in the cycle, capital rotation, policy and regulation, and where "
            "this theme sits in its adoption curve. Say whether the macro "
            "backdrop is a tailwind, a headwind, or neutral for this name over "
            "the client's horizon, and what would change your read."
        ),
    },
    {
        "key": "risk",
        "name": "Risk Agent",
        "round": 2,
        "brief": (
            "You are RISK. You have read the opening arguments. You do not care "
            "who is more persuasive — you care what this does to the BOOK. "
            "Judge concentration, correlation with what is already owned, the "
            "drawdown this could inflict, and whether the stop is survivable. "
            "The desk's standing limits are in the data; treat them as binding. "
            "If taking this position would breach a limit, say so plainly."
        ),
    },
    {
        "key": "execution",
        "name": "Execution Agent",
        "round": 2,
        "brief": (
            "You are EXECUTION. You have read the opening arguments. Assume a "
            "decision to act may be made — your job is the mechanics. Where is "
            "the entry, and is it here or on a pullback to a specific level? "
            "Where does the exit go? Is there a binary event (earnings) to "
            "trade around? Is liquidity adequate? Should this be staged in "
            "tranches or taken at once? Be concrete about levels."
        ),
    },
]

_AGENT_SCHEMA = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
    '"position" (ONE word: BULLISH | BEARISH | NEUTRAL — your corner\'s '
    'verdict), '
    '"confidence" (integer 0-100: how strongly the DATA supports your case, '
    'not how hard you are arguing — be honest, a weak hand is useful to the '
    'judge), '
    '"points" (array of 3-5 strings: your argument, one specific claim per '
    'bullet, each citing a number or fact you were given), '
    '"strongest" (string: your single best point in one sentence). '
    'Every bullet is one self-contained sentence under 28 words.'
)

_JUDGE_SCHEMA = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
    '"verdict" (APPROVE or REJECT — APPROVE means the idea survived the '
    'debate and should reach the client, REJECT means it did not), '
    '"action" (ONE word, the standing call: BUY | ADD | HOLD | TRIM | SELL | '
    'AVOID | WATCH), '
    '"score" (integer 0-100: quality of the surviving case), '
    '"headline" (string: the ruling in one plain sentence under 18 words), '
    '"rationale" (array of 3-5 strings: WHICH arguments won and why, naming '
    'the agent, e.g. "Bear\'s margin point outweighs Bull\'s TAM case"), '
    '"dissent" (array of 1-3 strings: the strongest surviving objection to '
    'your own ruling — what would make you wrong), '
    '"entry" (string: a price level or "at market" or "" if not acting), '
    '"target" (string: a price level or ""), '
    '"stop" (string: a price level or ""). '
    'Every bullet is one self-contained sentence under 28 words. '
    'You must name at least one agent you OVERRULED — a judge who agrees with '
    'everyone has not judged anything.'
)


# -------------------------------------------------------------------- store
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
        print(f"[debate] persist failed: {exc!r}")


def get_cached(symbol: str, max_age: int = CACHE_TTL) -> dict | None:
    d = _load().get((symbol or "").upper())
    if not d:
        return None
    if time.time() - float(d.get("ts", 0)) > max_age:
        return None
    return d


def history(limit: int = 20) -> list[dict]:
    """Most recent debates across all symbols, newest first."""
    items = sorted(_load().values(), key=lambda x: -float(x.get("ts", 0)))
    return [
        {k: v for k, v in d.items() if k != "transcript"}
        for d in items[:limit]
    ]


# ------------------------------------------------------------------- parsing
def _json_from(raw: str) -> dict:
    """Pull the JSON object out of a model reply that may be fenced or prosed."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        obj = json.loads(text[start : end + 1])
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clamp_int(val, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(float(val))))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------- facts
def _facts(symbol: str) -> tuple[str, object]:
    """The shared evidence pack every agent argues over."""
    report = pf_service.build_report(symbol)
    summary, held = pf_service.portfolio_summary()

    holding = next((r for r in held if r.symbol == report.symbol), None)
    if holding is not None:
        pos = (
            f"HELD: {holding.shares:g} shares, market value "
            f"${holding.market_value:,.0f} "
            f"({(holding.market_value or 0) / summary.total_market_value * 100:.1f}% "
            f"of the book), unrealized {holding.unrealized_pl_pct:+.1f}%."
        )
    else:
        pos = "NOT HELD — this is a candidate, not a position."

    plan = risk_service.plan_for(report, summary.total_market_value, summary.cash)
    sizing = (
        f"DESK SIZING (deterministic, not yours to change): "
        f"stop ${plan.stop} ({plan.stop_basis}), "
        f"size ${plan.dollars:,.0f} ({plan.pct_of_equity:.1f}% of equity), "
        f"risking ${plan.risk_amount:,.0f}."
        if plan.dollars
        else f"DESK SIZING: {plan.note}"
    )

    others = ", ".join(
        f"{r.symbol} {(r.market_value or 0) / summary.total_market_value * 100:.0f}%"
        for r in sorted(held, key=lambda r: -(r.market_value or 0))[:10]
    )

    block = "\n\n".join(
        x
        for x in [
            advisor._facts_from_report(report),
            pos,
            sizing,
            f"REST OF THE BOOK: {others}",
            risk_service.facts_block(),
            stance_service.block(report.symbol, report.quote.price),
            _journal_block(report.symbol),
        ]
        if x
    )
    return block, report


def _journal_block(symbol: str) -> str:
    """What the client has actually DONE in this name lately.

    The per-symbol counterpart of `journal.facts_block()`, which renders the
    whole book — correct for the brief, but noise in a debate about one name.
    Without it the desk re-argues a trade the client already made, the same
    statelessness that made the brief nag before the action ledger existed."""
    rows = [e for e in journal.list_entries(90) if (e.get("symbol") or "").upper() == symbol]
    if not rows:
        return ""
    lines = ["RECENT CLIENT ACTIONS IN THIS NAME (do not re-recommend what is done):"]
    for e in rows[:6]:
        qty = f" {e['shares']:g}sh" if e.get("shares") else ""
        px = f" @ ${e['price']}" if e.get("price") else ""
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"- {e.get('date')}: {str(e.get('action', '')).upper()}{qty}{px}{note}")
    return "\n".join(lines)


# --------------------------------------------------------------------- agents
def _run_agent(agent: dict, symbol: str, facts: str, prior: str = "") -> dict:
    prompt = (
        f"{agent['brief']}\n\n"
        f"The desk is debating {symbol}. Here is the evidence pack every agent "
        f"is working from. Cite only these numbers; never invent data.\n\n"
        f"{facts}\n\n"
        f"{prior}"
        f"{_AGENT_SCHEMA}"
    )
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    obj = _json_from(raw or "")
    position = str(obj.get("position", "") or "").strip().upper()
    if position not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        position = "NEUTRAL"
    return {
        "key": agent["key"],
        "name": agent["name"],
        "round": agent["round"],
        "position": position,
        "confidence": _clamp_int(obj.get("confidence"), 0, 100, 50),
        "points": advisor._as_bullets(obj.get("points")),
        "strongest": str(obj.get("strongest", "") or "").strip(),
        "ok": bool(raw),
    }


def _prior_block(round1: list[dict]) -> str:
    lines = ["OPENING ARGUMENTS FROM ROUND 1 — respond to these:"]
    for a in round1:
        if not a["points"]:
            continue
        lines.append(
            f"\n{a['name']} ({a['position']}, confidence {a['confidence']}):"
        )
        lines.extend(f"  - {p}" for p in a["points"])
    return "\n".join(lines) + "\n\n"


def _judge(symbol: str, facts: str, agents: list[dict]) -> dict:
    transcript = []
    for a in agents:
        transcript.append(
            f"\n{a['name']} — {a['position']}, confidence {a['confidence']}:"
        )
        transcript.extend(f"  - {p}" for p in a["points"])

    prompt = (
        f"{advisor._PERSONA}\n\n"
        f"You are chairing the desk. Five specialists have argued {symbol}. "
        f"Your job is to RULE, not to summarize: decide which arguments "
        f"actually survive scrutiny and which are noise, then give the client "
        f"one clear call. Weigh CONFIDENCE and EVIDENCE, not rhetoric — an "
        f"agent arguing hard on thin data should lose to one arguing quietly "
        f"on strong data.\n\n"
        f"EVIDENCE PACK:\n{facts}\n\n"
        f"THE DEBATE:{''.join(transcript)}\n\n"
        f"Position size is already fixed by the risk desk — do NOT restate or "
        f"change it. Rule on WHETHER, and on the levels.\n\n"
        f"{_JUDGE_SCHEMA}"
    )
    raw, _ = advisor._run_claude(prompt)      # default = best model
    obj = _json_from(raw or "")

    verdict = str(obj.get("verdict", "") or "").strip().upper()
    if verdict not in {"APPROVE", "REJECT"}:
        verdict = "REJECT"
    action = str(obj.get("action", "") or "").strip().upper().split()
    action = action[0] if action and action[0] in _VALID_ACTIONS else "WATCH"

    return {
        "verdict": verdict,
        "action": action,
        "score": _clamp_int(obj.get("score"), 0, 100, 0),
        "headline": str(obj.get("headline", "") or "").strip(),
        "rationale": advisor._as_bullets(obj.get("rationale")),
        "dissent": advisor._as_bullets(obj.get("dissent")),
        "entry": str(obj.get("entry", "") or "").strip(),
        "target": str(obj.get("target", "") or "").strip(),
        "stop": str(obj.get("stop", "") or "").strip(),
        "ok": bool(raw),
    }


# ----------------------------------------------------------------------- run
def convene(symbol: str, force: bool = False) -> dict:
    """Run a full debate on `symbol`. Six CLI calls — never call this on a poll."""
    sym = (symbol or "").upper()
    if not force:
        cached = get_cached(sym)
        if cached:
            return cached

    if not settings.ADVISOR_ENABLED:
        return {
            "symbol": sym,
            "ts": time.time(),
            "engine": "disabled",
            "error": "Advisor is disabled — the desk cannot convene.",
            "agents": [],
            "verdict": None,
        }

    facts, report = _facts(sym)

    # Round 1: the three opening arguments are independent, so run them at once.
    r1_agents = [a for a in AGENTS if a["round"] == 1]
    with ThreadPoolExecutor(max_workers=len(r1_agents)) as pool:
        round1 = list(pool.map(lambda a: _run_agent(a, sym, facts), r1_agents))

    # Round 2: these must SEE round 1, so they follow it (still concurrent).
    prior = _prior_block(round1)
    r2_agents = [a for a in AGENTS if a["round"] == 2]
    with ThreadPoolExecutor(max_workers=len(r2_agents)) as pool:
        round2 = list(pool.map(lambda a: _run_agent(a, sym, facts, prior), r2_agents))

    agents = round1 + round2
    ruling = _judge(sym, facts, agents)

    live = [a for a in agents if a["ok"]]
    bulls = sum(1 for a in live if a["position"] == "BULLISH")
    bears = sum(1 for a in live if a["position"] == "BEARISH")

    summary, _held = pf_service.portfolio_summary()
    plan = risk_service.plan_for(report, summary.total_market_value, summary.cash)

    result = {
        "symbol": sym,
        "name": report.quote.name,
        "price": report.quote.price,
        "ts": time.time(),
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "claude" if ruling["ok"] else "unavailable",
        "agents": agents,
        "agents_reporting": len(live),
        "tally": {"bullish": bulls, "bearish": bears,
                  "neutral": len(live) - bulls - bears},
        "verdict": ruling["verdict"],
        "action": ruling["action"],
        "score": ruling["score"],
        "headline": ruling["headline"],
        "rationale": ruling["rationale"],
        "dissent": ruling["dissent"],
        "entry": ruling["entry"],
        "target": ruling["target"],
        "stop": ruling["stop"],
        "sizing": plan.model_dump(),
        "error": None if ruling["ok"] else
                 "The judge could not be reached; agent arguments are shown "
                 "without a ruling.",
    }

    # One voice across the app: the ruling becomes the standing call, so the
    # dashboard and the stock page can't contradict the desk.
    if ruling["ok"] and ruling["headline"]:
        stance_service.set_stance(
            sym, ruling["action"],
            headline=ruling["headline"],
            thesis=" ".join(ruling["rationale"])[:400],
            target=ruling["target"], stop=ruling["stop"],
            source="debate", price=report.quote.price,
        )

    with _lock:
        d = _load()
        d[sym] = result
        # Bound the file: keep the 60 most recent debates.
        if len(d) > 60:
            for k, _ in sorted(d.items(), key=lambda kv: float(kv[1].get("ts", 0)))[:len(d) - 60]:
                d.pop(k, None)
        _save(d)
    return result
