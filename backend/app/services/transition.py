"""Transition plan — the sequenced path from the book you have to the one you want.

Everything else in this app diagnoses. The Clean Sheet says where you should
be, the Risk Desk says how much to size, the Debate says whether an idea
survives scrutiny. None of them tell you what to SELL to fund what to BUY, in
what order, at what price. Diagnosis you cannot act on is not advice.

This is the bridge. It is deliberately three layers:

  DETERMINISTIC  the gap, the funding sources, the entry levels and the tax
                 treatment are computed in Python. They are arithmetic, and a
                 model asked to do arithmetic will occasionally invent it.
  MODEL          one call sequences those facts into ordered, triggered steps
                 with reasoning. Judgement is the part worth a model.
  MONITORED      activating the plan puts every target on the watchlist and
                 every entry level into watchpoints, so the existing scan,
                 signal and alert machinery starts tracking the future book
                 alongside the current one. The plan then tells you WHEN.

A rebalance out of a concentrated book is a campaign, not a trade. Nothing
here asks for the whole thing at once.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings
from . import advisor, cleansheet, journal, market_data, risk as risk_service
from . import portfolio as pf_service
from . import stance as stance_service
from . import strategy as strategy_service
from . import watchpoints

_FILE = settings.PORTFOLIO_FILE.parent / "transition.json"
_lock = threading.Lock()

# Long-term capital gains threshold. Below this a sale is short-term.
LONG_TERM_DAYS = 365
# Wash sale: repurchasing a name within this many days of a loss disallows it.
WASH_SALE_DAYS = 30
# A theme within this many points of target is close enough to leave alone.
TOLERANCE_PCT = 3.0


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
        print(f"[transition] persist failed: {exc!r}")


def last_plan() -> dict | None:
    return _load() or None


def completed_moves() -> list[dict]:
    """Steps already executed, PERSISTED ACROSS REBUILDS.

    A rebuild used to produce a brand-new plan that started again at step 1
    "sell immediately", silently discarding what had already been done — so
    the plan looked like it never saved. Completed moves now outlive the plan
    that contained them and are fed back into the next generation, the same
    action-ledger discipline the whole-book brief already uses.
    """
    return list(_load().get("completed") or [])


# ----------------------------------------------------------------- tax facts
def _first_buy_dates() -> dict[str, str]:
    """Earliest recorded buy per symbol, from the action journal.

    Holdings carry no purchase date, so this is the only lot information the
    app has. Where it is missing the holding period is reported as unknown
    rather than assumed — guessing it would misstate a real tax consequence.
    """
    out: dict[str, str] = {}
    for e in journal.list_entries(3650):
        if str(e.get("action", "")).lower() != "buy":
            continue
        sym = (e.get("symbol") or "").upper()
        d = e.get("date")
        if sym and d and (sym not in out or d < out[sym]):
            out[sym] = d
    return out


def _tax_note(pl_pct: float | None, first_buy: str | None) -> dict:
    """What selling this position would actually do, tax-wise."""
    held_days = None
    if first_buy:
        try:
            t = time.mktime(time.strptime(first_buy, "%Y-%m-%d"))
            held_days = int((time.time() - t) / 86400)
        except ValueError:
            held_days = None

    if held_days is None:
        term = "unknown"
    elif held_days >= LONG_TERM_DAYS:
        term = "long"
    else:
        term = "short"

    at_loss = (pl_pct or 0) < 0
    if at_loss:
        detail = (
            "Selling books a loss you can use to offset gains"
            + (" — short-term, which offsets the most expensive gains first."
               if term == "short" else
               " — long-term." if term == "long" else ".")
            + f" Don't rebuy within {WASH_SALE_DAYS} days or the loss is disallowed."
        )
    else:
        detail = (
            "Selling books a taxable gain"
            + (f" — SHORT-term at {held_days} days held, taxed as ordinary income; "
               f"waiting until {LONG_TERM_DAYS} days would cut the rate."
               if term == "short" and held_days is not None else
               " — long-term, at the lower rate." if term == "long" else ".")
        )
    return {"at_loss": at_loss, "term": term, "held_days": held_days,
            "detail": detail}


# ------------------------------------------------------------------- the gap
def _target() -> tuple[dict[str, float], list[dict], str]:
    """(theme -> target pct, target picks, source). Clean Sheet wins; it has names."""
    cs = cleansheet.last_result()
    if cs and cs.get("allocation"):
        alloc = {str(a["theme"]): float(a.get("pct") or 0) for a in cs["allocation"]}
        return alloc, list(cs.get("picks") or []), "cleansheet"
    doc = strategy_service.load() or {}
    if doc.get("approved") and doc.get("allocation_targets"):
        return ({str(k): float(v) for k, v in doc["allocation_targets"].items()},
                [], "strategy")
    return {}, [], "none"


def analyse(full: bool = True) -> dict:
    """The deterministic half: gap, funding sources, acquisition targets.

    full=False skips the per-target price/stop lookup, which is the expensive
    part — it builds a full report (history + analyst + news) for every
    acquisition target. That cost is fine when generating a plan; paying it on
    every page load is what made GET slow enough to hit the tunnel's ~100s
    ceiling, and a failed GET looked like "no plan" and invited a rebuild.
    """
    summary, held = pf_service.portfolio_summary()
    equity = summary.total_market_value or 0.0
    target_theme, picks, source = _target()
    dates = _first_buy_dates()

    current_theme: dict[str, float] = {}
    for theme, val in (summary.by_theme or {}).items():
        current_theme[theme] = val / equity * 100 if equity else 0.0

    themes = sorted(set(target_theme) | set(current_theme),
                    key=lambda t: (target_theme.get(t, 0) - current_theme.get(t, 0)))
    gap = [{
        "theme": t,
        "target_pct": round(target_theme.get(t, 0.0), 1),
        "current_pct": round(current_theme.get(t, 0.0), 1),
        "delta": round(target_theme.get(t, 0.0) - current_theme.get(t, 0.0), 1),
    } for t in themes]

    # Drift: the share of the book that must change hands to reach target.
    drift = round(sum(abs(g["delta"]) for g in gap) / 2, 1)

    held_syms = {r.symbol for r in held if (r.market_value or 0) > 0}
    pick_syms = {str(p.get("symbol", "")).upper() for p in picks}

    # ---- funding sources: overweight themes, worst positions first ---------
    over = {g["theme"]: -g["delta"] for g in gap if g["delta"] < -TOLERANCE_PCT}
    funding = []
    for r in sorted(held, key=lambda r: -(r.market_value or 0)):
        mv = r.market_value or 0
        if mv <= 0:
            continue
        theme = r.theme or "Other"
        if theme not in over:
            continue
        weight = mv / equity * 100 if equity else 0
        # Trim proportionally to how overweight the theme is, capped at the
        # position. Keeping names the target book still wants.
        theme_val = (summary.by_theme or {}).get(theme, 0) or 1
        raise_pct = over[theme] / (theme_val / equity * 100) if equity else 0
        suggested = round(min(mv, mv * min(1.0, raise_pct)), 2)
        st = stance_service.get(r.symbol) or {}
        funding.append({
            "symbol": r.symbol,
            "theme": theme,
            "value": round(mv, 2),
            "weight_pct": round(weight, 1),
            "pl_pct": round(r.unrealized_pl_pct or 0, 1),
            "suggested_trim": suggested,
            "in_target_book": r.symbol in pick_syms,
            "standing_call": st.get("action"),
            "tax": _tax_note(r.unrealized_pl_pct, dates.get(r.symbol)),
        })
    # Sell what the target book does NOT want first, then the weakest.
    funding.sort(key=lambda f: (f["in_target_book"], f["pl_pct"]))

    # ---- acquisition targets ----------------------------------------------
    wanted = [str(p.get("symbol", "")).upper() for p in picks]
    wanted = [s for s in wanted if s and s not in held_syms]
    if full and wanted:
        # One parallel prefetch instead of N serial cold fetches.
        try:
            market_data.warm_cache(wanted, max_workers=8)
        except Exception:
            pass

    acquire = []
    for p in picks:
        sym = str(p.get("symbol", "")).upper()
        if not sym or sym in held_syms:
            continue
        want = float(p.get("pct") or 0) / 100 * equity
        price = None
        stop = None
        if full:
            try:
                rep = pf_service.build_report(sym)
                price = rep.quote.price
                stop = risk_service.plan_for(rep, equity, cash=equity).stop
            except Exception:
                pass
        acquire.append({
            "symbol": sym,
            "theme": str(p.get("theme", "")),
            "target_pct": float(p.get("pct") or 0),
            "target_dollars": round(want, 2),
            "price": price,
            "stop": stop,
            "why": str(p.get("why", "")),
        })
    acquire.sort(key=lambda a: -a["target_pct"])

    return {
        "equity": round(equity, 2),
        "cash": round(summary.cash or 0, 2),
        "target_source": source,
        "drift_pct": drift,
        "gap": gap,
        "funding": funding,
        "acquire": acquire,
        "total_return_pct": round(summary.total_return_pct or 0, 2),
    }


# --------------------------------------------------------------- the sequence
_SCHEMA = (
    'Respond with ONLY a JSON object, no markdown: '
    '"headline" (string: the plan in one plain sentence under 20 words), '
    '"approach" (string: 2-3 sentences on the sequencing logic — why this '
    'order, and what has to be true before the next step), '
    '"steps" (array of 3-6 objects, in execution order: '
    '{"n": integer, '
    '"trigger": string — the CONDITION to wait for, e.g. "AVGO recovers to '
    '$390" or "immediately"; be concrete and use a price where possible, '
    '"sell": string — the sell order in plain words with $ amount and ticker, '
    'or "" if this step buys only, '
    '"buy": string — the buy order in plain words with $ amount, ticker and '
    'level, or "" if this step sells only, '
    '"buy_symbol": string — just the ticker being bought, or "", '
    '"buy_level": number — the price to buy at, or 0, '
    '"sell_symbol": string — just the ticker being sold, or "", '
    '"sell_level": number — the price to sell at, or 0, '
    '"why": string — one sentence on what this step accomplishes, '
    '"realizes": string — the tax consequence in plain words, or ""}), '
    '"guardrails" (array of 2-4 strings: what would make you STOP executing '
    'this plan), '
    '"first_move" (string: the single thing to do next, in one sentence). '
    'Every string is one self-contained sentence under 30 words.'
)


def _prompt(a: dict) -> str:
    fund_lines = "\n".join(
        f"  {f['symbol']} ({f['theme']}): ${f['value']:,.0f}, {f['weight_pct']:.1f}% of book, "
        f"P/L {f['pl_pct']:+.1f}%, "
        f"{'IN the target book - trim only' if f['in_target_book'] else 'NOT in the target book'}"
        f"{', standing call ' + f['standing_call'] if f.get('standing_call') else ''}. "
        f"{f['tax']['detail']}"
        for f in a["funding"][:10]
    ) or "  (nothing flagged as overweight)"

    acq_lines = "\n".join(
        f"  {t['symbol']} ({t['theme']}): want ${t['target_dollars']:,.0f} "
        f"({t['target_pct']:.0f}% of book), trades at "
        f"${t['price'] if t['price'] else 'n/a'}"
        f"{', stop $' + format(t['stop'], '.2f') if t.get('stop') else ''}. "
        f"{t['why']}"
        for t in a["acquire"][:10]
    ) or "  (no acquisition targets - run the Clean Sheet first)"

    gap_lines = "\n".join(
        f"  {g['theme']}: now {g['current_pct']:.1f}%, target {g['target_pct']:.1f}% "
        f"({g['delta']:+.1f})"
        for g in a["gap"] if abs(g["delta"]) >= 1
    )

    done = completed_moves()
    done_block = ""
    if done:
        done_block = (
            "ALREADY EXECUTED — these moves are DONE. Do NOT recommend them "
            "again, and treat the proceeds as already spent:\n"
            + "\n".join(
                f"  {c.get('done_at', '')[:10]}: "
                + " / ".join(x for x in (c.get("sell"), c.get("buy")) if x)
                for c in done[-12:]
            )
            + "\n\n"
        )

    return (
        f"{advisor._PERSONA}\n\n"
        f"Build a SEQUENCED REBALANCE PLAN. The client is over-concentrated, is "
        f"down {a['total_return_pct']:+.1f}% overall, and has ${a['cash']:,.0f} in "
        f"cash — so every purchase must be FUNDED BY A SALE. They have "
        f"explicitly accepted that taking a loss to fund a better position can "
        f"be worth it. Your job is the path, not the destination: what to sell, "
        f"what to buy, in what order, and what has to happen first.\n\n"
        f"BOOK: ${a['equity']:,.0f} across the positions below. "
        f"{a['drift_pct']:.0f}% of the book has to change hands to reach target.\n\n"
        f"{done_block}"
        f"ALLOCATION GAP:\n{gap_lines}\n\n"
        f"FUNDING SOURCES (overweight positions that could be trimmed):\n{fund_lines}\n\n"
        f"ACQUISITION TARGETS (wanted, not owned):\n{acq_lines}\n\n"
        f"RULES FOR THIS PLAN:\n"
        f"- Every buy must be funded by a sell in the SAME or an EARLIER step. "
        f"Never propose spending money that does not exist.\n"
        f"- Sell what the target book does not want BEFORE trimming what it does.\n"
        f"- Do NOT dump a concentrated position in one move. Stage it.\n"
        f"- Prefer selling into strength: waiting for a bounce beats selling a "
        f"position at its low, unless the thesis is broken.\n"
        f"- Realising a LOSS is acceptable and often useful here — say so "
        f"plainly when it is, including the wash-sale constraint.\n"
        f"- 3 to 6 steps. This is a campaign over weeks, not a single day.\n"
        f"- Use the REAL prices given. Never invent a level.\n\n"
        f"{_SCHEMA}"
    )


def generate(force: bool = True) -> dict:
    a = analyse()
    if a["target_source"] == "none":
        return {"ts": time.time(), "engine": "blocked", "analysis": a,
                "error": "No target to move toward — build a Clean Sheet or "
                         "approve a Strategy first.", "steps": []}
    if not settings.ADVISOR_ENABLED:
        return {"ts": time.time(), "engine": "disabled", "analysis": a,
                "error": "Advisor is disabled.", "steps": []}

    raw, _ = advisor._run_claude(_prompt(a))
    if not raw:
        return {"ts": time.time(), "engine": "unavailable", "analysis": a,
                "error": "The desk could not be reached — try again.", "steps": []}

    text = raw.strip()
    s, e = text.find("{"), text.rfind("}")
    try:
        obj = json.loads(text[s : e + 1]) if s != -1 and e > s else {}
    except json.JSONDecodeError:
        obj = {}

    prior = _load()
    completed = list(prior.get("completed") or [])
    done_sigs = {c.get("sig") for c in completed}

    steps = []
    for i, st in enumerate(obj.get("steps") or [], start=1):
        if not isinstance(st, dict):
            continue
        step = {
            "n": int(st.get("n") or i),
            "trigger": str(st.get("trigger", "")),
            "sell": str(st.get("sell", "")),
            "buy": str(st.get("buy", "")),
            "buy_symbol": str(st.get("buy_symbol", "")).upper(),
            "buy_level": float(st.get("buy_level") or 0),
            "sell_symbol": str(st.get("sell_symbol", "")).upper(),
            "sell_level": float(st.get("sell_level") or 0),
            "why": str(st.get("why", "")),
            "realizes": str(st.get("realizes", "")),
        }
        # A rebuild renumbers the steps, so done-state is carried by move
        # identity rather than by position in the list.
        step["done"] = _signature(step) in done_sigs
        steps.append(step)
    steps.sort(key=lambda x: x["n"])

    result = {
        "ts": time.time(),
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "claude",
        "headline": str(obj.get("headline", "")),
        "approach": str(obj.get("approach", "")),
        "first_move": str(obj.get("first_move", "")),
        "steps": steps,
        "guardrails": advisor._as_bullets(obj.get("guardrails")),
        "analysis": a,
        # Both survive a rebuild: the execution ledger, and the fact that the
        # targets are already on the watchlist with live triggers.
        "completed": completed,
        "activated": bool(prior.get("activated")),
        "activated_at": prior.get("activated_at"),
        "watched": prior.get("watched") or [],
        "watchpoints_created": prior.get("watchpoints_created") or 0,
        "error": None,
    }
    with _lock:
        _save(result)
    return result


# ------------------------------------------------------------------ activate
def activate() -> dict:
    """Put the plan under active monitoring.

    Adds every acquisition target to the WATCHLIST so the existing scan,
    conviction and news machinery tracks the future book beside the current
    one, and turns each step's price into a watchpoint so the app can say WHEN
    rather than the client having to remember to look.
    """
    plan = _load()
    if not plan or not plan.get("steps"):
        return {"error": "No plan to activate.", "watched": [], "watchpoints": 0}

    a = plan.get("analysis") or {}
    added: list[str] = []
    cfg = pf_service.load_portfolio()
    existing = {i["symbol"].upper() for i in
                cfg.get("holdings", []) + cfg.get("watchlist", [])}
    for t in a.get("acquire", []):
        sym = t["symbol"]
        if sym and sym not in existing:
            cfg.setdefault("watchlist", []).append({"symbol": sym})
            existing.add(sym)
            added.append(sym)
    if added:
        pf_service.save_portfolio(cfg)

    made = 0
    for st in plan["steps"]:
        if st.get("buy_symbol") and st.get("buy_level"):
            try:
                watchpoints.add(st["buy_symbol"], "price_below",
                                float(st["buy_level"]),
                                note=f"Transition step {st['n']}: {st['buy']}"[:180],
                                side="buy")
                made += 1
            except Exception as exc:
                print(f"[transition] watchpoint failed: {exc!r}")
        if st.get("sell_symbol") and st.get("sell_level"):
            try:
                watchpoints.add(st["sell_symbol"], "price_above",
                                float(st["sell_level"]),
                                note=f"Transition step {st['n']}: {st['sell']}"[:180],
                                side="sell")
                made += 1
            except Exception as exc:
                print(f"[transition] watchpoint failed: {exc!r}")

    plan["activated"] = True
    plan["activated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    plan["watched"] = added
    plan["watchpoints_created"] = made
    with _lock:
        _save(plan)
    return {"watched": added, "watchpoints": made, "error": None}


def _signature(st: dict) -> str:
    """Identity of a move, stable across rebuilds that renumber the steps."""
    return "|".join([
        str(st.get("sell_symbol", "")).upper(),
        str(st.get("buy_symbol", "")).upper(),
        str(st.get("sell", ""))[:60],
        str(st.get("buy", ""))[:60],
    ])


def set_step_done(n: int, done: bool = True) -> dict | None:
    with _lock:
        plan = _load()
        completed = list(plan.get("completed") or [])
        found = None
        for st in plan.get("steps", []):
            if int(st.get("n", 0)) != n:
                continue
            st["done"] = bool(done)
            found = st
            sig = _signature(st)
            completed = [c for c in completed if c.get("sig") != sig]
            if done:
                completed.append({
                    "sig": sig,
                    "sell": st.get("sell", ""),
                    "buy": st.get("buy", ""),
                    "done_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
            break
        if found is not None:
            plan["completed"] = completed
            _save(plan)
        return found


def facts_block() -> str:
    """The standing plan, for advisor prompts.

    Gated on a plan EXISTING, not on it being activated. Activation only
    controls monitoring (watchlist + triggers); it says nothing about whether
    the plan is the client's standing intent. Gating on it meant a generated
    plan was invisible to the brief, so the two surfaces cheerfully issued
    contradictory orders on the same book — which is exactly what a shared
    ledger exists to prevent.
    """
    plan = _load()
    if not plan or not plan.get("steps"):
        return ""
    state = "ACTIVE" if plan.get("activated") else "DRAFT (not yet activated)"
    open_steps = [s for s in plan["steps"] if not s.get("done")]
    done = [s for s in plan["steps"] if s.get("done")]

    lines = [
        f"STANDING TRANSITION PLAN [{state}] — the client has a sequenced "
        f"rebalance on file. This is the agreed campaign for this book. Stay "
        f"CONSISTENT with it: do not propose trades that contradict it, and do "
        f"not re-recommend a step already executed. If you genuinely disagree "
        f"with a step, say so explicitly ('the plan says X; I'd revise it "
        f"because Y') rather than quietly issuing a different order."
    ]
    if plan.get("headline"):
        lines.append(f"- Plan: {plan['headline']}")
    for s in open_steps[:6]:
        parts = " / ".join(x for x in (s.get("sell"), s.get("buy")) if x)
        lines.append(f"- OUTSTANDING step {s['n']} (when {s['trigger']}): {parts}")
    for c in (plan.get("completed") or [])[-6:]:
        parts = " / ".join(x for x in (c.get("sell"), c.get("buy")) if x)
        lines.append(f"- ALREADY DONE {c.get('done_at', '')[:10]}: {parts}")
    if not open_steps and done:
        lines.append("- Every step is complete; the rebalance is finished.")
    return "\n".join(lines)
