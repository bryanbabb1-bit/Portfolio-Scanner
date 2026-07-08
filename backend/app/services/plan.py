"""Sequenced game plan — reconcile every staged move into ONE gated plan.

The dashboard used to show pinned to-dos, armed triggers and conviction
signals as independent rows, so the user couldn't tell that (e.g.) two buys
are meant to be funded by a trim that hasn't fired yet. This service reads all
of those sources plus the live book and the strategy's cash floor, then works
out for each move:

  * its PRICE GATE — the level that has to hit, and how far away it is;
  * its FUNDING GATE — whether a buy has to wait for a sale to free cash
    (because spending idle cash would breach the dry-powder floor);
  * its STATUS — ready to act on now, or waiting (and on what).

Everything here is deterministic (no Claude call) so it stays in sync with the
live tape on every refresh.
"""
from __future__ import annotations

import re

from . import conviction, pins as pins_svc, portfolio as pf
from . import strategy as strat_svc, watchpoints as wp_svc

_LEVEL_RE = re.compile(
    r"(?:near|at|above|below|over|under|to|reaches?|hits?|past)\s+\$?([\d,]+(?:\.\d{1,2})?)",
    re.I,
)
_AMOUNT_RE = re.compile(
    r"(?:buy|add|accumulate|start|deploy|scoop|sell|trim|cut|reduce|put)\s+\$?([\d,]+(?:\.\d{1,2})?)",
    re.I,
)
_STOP_WORDS = ("stop", "drops", "break", "loses", "below", "under", "falls")
_FUND_WORDS = ("trim cash", "proceeds", "using the trim", "from the trim",
               "with the trim", "sale proceeds", "freed cash", "trim proceeds")


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _side(text: str) -> str:
    w = text.strip().lower()
    if re.match(r"^\W*(buy|add|accumulate|start|deploy|scoop|open|put)\b", w):
        return "buy"
    if re.match(r"^\W*(trim|cut|reduce|lighten|pare|sell|exit|close|dump|offload)\b", w):
        return "sell"
    if re.match(r"^\W*(hold|keep|stay|watch|wait|do nothing|stand)\b", w):
        return "hold"
    if any(k in w for k in ("buy", "add ", "accumulate")):
        return "buy"
    if any(k in w for k in ("trim", "sell", "cut ")):
        return "sell"
    return "hold"


def _find_symbol(text: str, known: set[str]) -> str | None:
    """Pull a ticker out of an order like 'Buy $150 NVDA near $191' when the
    move wasn't stored against a symbol (brief pins often aren't)."""
    for sym in sorted(known, key=len, reverse=True):
        if re.search(rf"\b{re.escape(sym)}\b", text):
            return sym
    return None


def _parse_amount(text: str) -> float | None:
    m = _AMOUNT_RE.search(text)
    return _num(m.group(1)) if m else None


def _parse_level(text: str) -> float | None:
    m = _LEVEL_RE.search(text)
    return _num(m.group(1)) if m else None


def _price_gate(side: str, text: str, level: float | None,
                current: float | None) -> dict | None:
    """Where does the price need to be, and is it there yet?"""
    if level is None or current is None or current <= 0:
        return None
    low = text.lower()
    if side == "buy":
        direction, met = "fall", current <= level * 1.003
    else:  # sell / trim
        if any(k in low for k in _STOP_WORDS):
            direction, met = "fall", current <= level * 1.003
        else:  # trim into strength — needs a bounce up to the level
            direction, met = "rise", current >= level * 0.997
    return {
        "level": round(level, 2),
        "current": round(current, 2),
        "distance_pct": round((level / current - 1) * 100, 1),
        "direction": direction,
        "met": met,
    }


def _wp_gate(w: dict, current: float | None, rsi: float | None) -> dict | None:
    kind = w["kind"]
    level = w["level"]
    if kind.startswith("price"):
        if current is None or current <= 0:
            return None
        met = current >= level if kind == "price_above" else current <= level
        return {
            "level": round(level, 2),
            "current": round(current, 2),
            "distance_pct": round((level / current - 1) * 100, 1),
            "direction": "rise" if kind == "price_above" else "fall",
            "met": met,
            "rsi": False,
        }
    if rsi is None:
        return None
    met = rsi >= level if kind == "rsi_above" else rsi <= level
    return {
        "level": level, "current": round(rsi, 1),
        "distance_pct": round(level - rsi, 1),
        "direction": "rise" if kind == "rsi_above" else "fall",
        "met": met, "rsi": True,
    }


def _floor(strategy: dict | None, book: float) -> tuple[float, float]:
    """Dry-powder floor in dollars and percent, from the strategy's cash
    allocation target (falling back to 15%)."""
    pct = 15.0
    if strategy:
        for k, v in (strategy.get("allocation_targets") or {}).items():
            if "cash" in k.lower():
                try:
                    pct = float(v)
                except (TypeError, ValueError):
                    pass
                break
    return round(book * pct / 100), pct


def build_plan() -> dict:
    summary, reports = pf.portfolio_summary()
    price_map = {r.symbol: r.quote.price for r in reports}
    rsi_map = {r.symbol: (r.indicators.rsi if r.indicators else None) for r in reports}
    known = set(price_map)
    book = summary.total_market_value
    cash = summary.cash
    strategy = strat_svc.load()
    floor, floor_pct = _floor(strategy, book)
    deployable = round(max(0.0, cash - floor))

    raw: list[dict] = []

    # 1) armed triggers — explicit price/RSI gates
    for w in wp_svc.list_watchpoints(include_triggered=False):
        if w.get("status") != "armed":
            continue
        sym = w["symbol"]
        cur = price_map.get(sym)
        raw.append({
            "id": f"wp:{w['id']}", "wp_id": w["id"], "source": "trigger",
            "symbol": sym, "side": w.get("side") or _side(w.get("note", "")),
            "text": w.get("note") or wp_svc.condition_str(w),
            "amount": _parse_amount(w.get("note", "")),
            "gate": _wp_gate(w, cur, rsi_map.get(sym)),
            "rank": 3,
        })

    # 2) pinned reminders — parse level/amount out of the order text
    for p in pins_svc.list_pins():
        if p.get("status") != "open":
            continue
        sym = p.get("symbol") or _find_symbol(p["text"], known)
        side = _side(p["text"])
        level = _parse_level(p["text"])
        cur = price_map.get(sym) if sym else None
        raw.append({
            "id": f"pin:{p['id']}", "pin_id": p["id"], "source": "pin",
            "symbol": sym, "side": side, "text": p["text"],
            "amount": _parse_amount(p["text"]),
            "gate": _price_gate(side, p["text"], level, cur),
            "rank": 2,
        })

    # 3) live conviction signals — competing buys/sells
    try:
        signals = [s for s in conviction.scan() if not s.get("dismissed")]
    except Exception:
        signals = []
    for s in signals:
        sym = s["symbol"]
        text = s.get("what") or s.get("headline") or ""
        # Trust the wording: a "skip/avoid/hold" enrichment is NOT a cash-raising
        # sell, so it must never become a funder. Fall back to the declared side
        # only when the text is genuinely neutral.
        side = _side(text)
        if side == "hold":
            sig_side = s.get("side")
            if sig_side in ("buy", "sell") and not re.match(
                    r"^\W*(skip|avoid|hold|don|no |not |wait|stay|steer)", text.lower()):
                side = sig_side
            else:
                continue
        level = _parse_level(s.get("entry") or "") or _parse_level(text)
        raw.append({
            "id": f"sig:{s['id']}", "source": "signal", "symbol": sym,
            "side": side, "text": text,
            "amount": _parse_amount(s.get("size") or "") or _parse_amount(text),
            "gate": _price_gate(side, text, level, price_map.get(sym)),
            "rank": 1,
        })

    # collapse duplicates (same symbol + side) — keep the richest record
    grouped: dict[tuple, dict] = {}
    for m in raw:
        key = (m["symbol"], m["side"])
        cur = grouped.get(key)
        if cur is None:
            grouped[key] = m
            continue
        better = (bool(m["gate"]), m["rank"]) > (bool(cur["gate"]), cur["rank"])
        keep, drop = (m, cur) if better else (cur, m)
        keep["amount"] = keep.get("amount") or drop.get("amount")
        grouped[key] = keep
    moves = list(grouped.values())

    queued_buys = round(sum(m["amount"] or 0 for m in moves if m["side"] == "buy"))
    below_floor = cash < floor

    # A funder is a real cash-RAISING sell (a trim into strength / "move to
    # cash") — never a protective stop, which only fires on a drop and doesn't
    # free discretionary cash. A buy is never funded by a sale of its OWN name.
    funders = [m["symbol"] for m in moves
               if m["side"] == "sell" and m["symbol"] and not _is_stop(m)]
    funder_ready = {m["symbol"] for m in moves
                    if m["side"] == "sell" and not _is_stop(m)
                    and (m.get("gate") is None or m["gate"]["met"])}

    guards, ready, waiting = [], [], []
    for m in moves:
        gate = m.get("gate")
        price_ready = (gate is None) or gate["met"]
        m["funded_by"] = None
        m["stop"] = _is_stop(m)

        # protective stops are standing risk guards, not to-dos or funders
        if m["stop"]:
            m["status"] = "guard"
            m["wait_reason"] = _stop_reason(m, gate)
            guards.append(m)
            continue

        reason = None
        if m["side"] == "buy":
            text_funded = any(k in m["text"].lower() for k in _FUND_WORDS)
            funder = next((f for f in funders if f != m["symbol"]), None)
            needs_sale = below_floor or text_funded
            if needs_sale and funder:
                m["funded_by"] = funder
            sale_ready = (m["funded_by"] in funder_ready) if m["funded_by"] else not needs_sale
            if not price_ready:
                reason = _price_reason(m, gate)
                if m["funded_by"] and not sale_ready:
                    reason += f" Then fund it from the {m['funded_by']} trim."
            elif needs_sale and not sale_ready:
                reason = (f"Funded by the {m['funded_by']} trim — do it once that frees cash."
                          if m["funded_by"]
                          else "Cash is below your floor — raise cash before adding.")
        else:  # trim / sell into strength / hold
            if not price_ready:
                reason = _price_reason(m, gate)

        m["status"] = "ready" if reason is None else "waiting"
        m["wait_reason"] = reason
        (ready if reason is None else waiting).append(m)

    order = {"sell": 0, "buy": 1, "hold": 2}
    ready.sort(key=lambda m: (order.get(m["side"], 3), abs((m.get("gate") or {}).get("distance_pct", 0))))
    waiting.sort(key=lambda m: (order.get(m["side"], 3), abs((m.get("gate") or {}).get("distance_pct", 999))))

    return {
        "dry_powder": round(cash),
        "floor": floor,
        "floor_pct": floor_pct,
        "below_floor": below_floor,
        "deployable": deployable,
        "queued_buys": queued_buys,
        "funded_by_sale": any(m.get("funded_by") for m in moves),
        "funders": funders,
        "ready": ready,
        "waiting": waiting,
        "guards": guards,
        "count": len(moves),
    }


def _is_stop(m: dict) -> bool:
    """A protective stop, not a cash-raising trim: 'stop' in the wording, or a
    sell that only triggers on a DROP."""
    if m["side"] != "sell":
        return False
    if "stop" in m["text"].lower():
        return True
    g = m.get("gate")
    return bool(g and g.get("direction") == "fall")


def _stop_reason(m: dict, gate: dict | None) -> str:
    sym = m["symbol"] or "the position"
    if gate:
        return (f"Protective stop — only sells {sym} if it drops to ${gate['level']:g} "
                f"({abs(gate['distance_pct']):g}% away); it won't touch your position otherwise.")
    return f"Protective stop on {sym}."


def _price_reason(m: dict, gate: dict | None) -> str:
    if gate is None:
        return "On a further move — no set level yet."
    sym = m["symbol"] or "it"
    away = abs(gate["distance_pct"])
    unit = "pts" if gate.get("rsi") else "%"
    if gate.get("rsi"):
        verb = "rise to" if gate["direction"] == "rise" else "fall to"
        return f"Waiting for {sym} RSI to {verb} {gate['level']:g} ({away:g} {unit} away)."
    verb = "dip to" if gate["direction"] == "fall" else "bounce to"
    return f"Waiting for {sym} to {verb} ${gate['level']:g} ({away:g}{unit} away)."
