"""Plan Watch — proactively re-evaluate STAGED plans (open pins) when the
market moves against their premise, so a stale order gets a second look BEFORE
it's executed.

This is the advisor lens applied to the client's own pending decisions, not
just to market signals: you staged a SELL as loss-control, the stock runs in
pre-market, and the right move flips to 'ride it as a profit play'. Without
this, that only happens if the client thinks to ask. Every scan, each open
pinned plan with a ticker is checked; a ~5% move against its baseline (or a
price level named in the plan being crossed) sends it to the advisor, and if
the advisor says the plan CHANGED, a RECONSIDER slap fires.
"""
from __future__ import annotations

import re
import time

from . import pins as pins_service

REEVAL_PCT = 0.05     # ~5% move against the plan (Bryan: balanced)
COOLDOWN_H = 8        # don't re-nudge the same pin within 8h unless it moves more
_LEVEL_RE = re.compile(r"\$\s*(\d{1,6}(?:\.\d{1,2})?)")


def _level_in(text: str) -> float | None:
    """First dollar-denominated level named in the plan text, e.g. '$672'."""
    for m in _LEVEL_RE.finditer(text or ""):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if v >= 1:
            return v
    return None


def check(price_by_symbol: dict) -> list[dict]:
    """price_by_symbol: {SYMBOL: current_price} gathered by the scan. Returns
    plan-reeval signal dicts (same shape as conviction signals) for plans whose
    premise the advisor judges to have changed."""
    out: list[dict] = []
    now = time.time()
    today = time.strftime("%Y-%m-%d")

    for pin in pins_service.list_pins():
        if pin.get("status") != "open":
            continue
        sym = pin.get("symbol")
        if not sym:
            continue

        price = price_by_symbol.get(sym)
        if price is None:
            try:
                from . import portfolio as pf
                q = pf.build_report(sym).quote
                if getattr(q, "source", "live") == "mock":
                    continue  # never act on mock fallback data
                price = q.price
            except Exception:
                continue

        base = pin.get("price_at_pin")
        if not base:
            # First time we've seen this plan — set the baseline, don't fire yet.
            pins_service.patch(pin["id"], price_at_pin=round(float(price), 2))
            continue

        move = (price - base) / base if base else 0.0
        level = _level_in(pin.get("text", ""))
        crossed = bool(level and min(base, price) <= level <= max(base, price)
                       and abs(price - base) > 1e-6)
        if abs(move) < REEVAL_PCT and not crossed:
            continue

        # Cooldown: only re-nudge if 8h passed OR it moved another 5% since the
        # last fire — a real shift, not the same alert every minute.
        fired_ts = pin.get("watch_fired_ts", 0)
        fired_price = pin.get("watch_fired_price", base)
        moved_since = abs(price - fired_price) / fired_price if fired_price else 1.0
        if fired_ts and (now - fired_ts) < COOLDOWN_H * 3600 and moved_since < REEVAL_PCT:
            continue

        try:
            from . import advisor
            verdict = advisor.reevaluate_plan(pin, float(base), float(price), move)
        except Exception as exc:
            print(f"[planwatch] reevaluate failed for {sym}: {exc!r}")
            continue

        if verdict.get("plan_status") != "changed":
            continue

        pins_service.patch(pin["id"], watch_fired_ts=now,
                           watch_fired_price=round(float(price), 2))
        action = str(verdict.get("action") or "HOLD").upper()
        side = "sell" if action in ("SELL", "TRIM", "AVOID") else "buy"
        out.append({
            "id": f"plan:{pin['id']}:{today}",
            "symbol": sym, "side": side, "rule": "plan-reeval",
            "label": "Reconsider staged plan",
            "headline": verdict.get("headline") or f"{sym}: your staged plan may have changed",
            "what": verdict.get("what") or "",
            "why": verdict.get("why") or [],
            "target": verdict.get("target", ""), "stop": verdict.get("stop", ""),
            "action": action, "price": round(float(price), 2),
            "plan_text": pin.get("text", ""),
            "move_pct": round(move * 100, 1),
            "theme": "Plan", "held": True, "dismissed": False,
            "data_source": verdict.get("data_source"),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": now,
        })
    return out
