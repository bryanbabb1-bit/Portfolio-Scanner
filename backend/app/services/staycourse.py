"""Stay-the-Course read — grounded reassurance for the long game.

Bryan's own insight: he struggles with patience and half his check-ins are
really a search for PERMISSION TO HOLD. This gives him one dependable place to
get that permission — but only when it's EARNED. It computes, with no Claude
call and no scan side-effects, whether this is genuinely a "hold" week (nothing
in the plan needs action, no critical alert) or an "act" week, and assembles
REAL facts that justify staying the course: how many holdings are still trending
up, progress toward the goal, a position he held from its low back up, booked
gains. The advisor narrates these (advisor.advise_stay_course); if Claude is
down, the deterministic reasons below stand on their own.

Alerts/signals are untouched — this never suppresses a warning. It only frames
the QUIET, which is exactly when impatience does its damage.
"""
from __future__ import annotations

from ..models.schemas import PortfolioAlert, PortfolioSummary, RiskMetrics, StockReport


def _held(reports: list[StockReport]) -> list[StockReport]:
    return [r for r in reports if (r.market_value or 0) > 0 and r.shares]


def _above_trend(reports: list[StockReport]) -> tuple[int, int]:
    """How many holdings sit above their 200-day line (healthy long-term trend)."""
    held = _held(reports)
    above = 0
    for r in held:
        sma = r.indicators.sma200
        if sma and r.quote.price and r.quote.price >= sma:
            above += 1
    return above, len(held)


def _resilience(reports: list[StockReport]) -> dict | None:
    """The holding most recovered from its 52-week low — proof patience pays.
    Prefer a currently-profitable name; fall back to the biggest recovery."""
    best = None
    best_profit = None
    for r in _held(reports):
        low = r.indicators.low_52w
        price = r.quote.price
        if not low or not price or price <= low:
            continue
        gain = (price - low) / low * 100
        cand = {"symbol": r.symbol, "low": round(low, 2),
                "price": round(price, 2), "gain_pct": round(gain, 1)}
        if best is None or gain > best["gain_pct"]:
            best = cand
        if (r.unrealized_pl_pct or 0) > 0 and (
                best_profit is None or gain > best_profit["gain_pct"]):
            best_profit = cand
    return best_profit or best


def _goal() -> dict | None:
    """No numeric goal any more.

    This read a target value off the approved strategy document. That document
    was removed — it drifted out of sync with the live brief and produced
    contradictory advice — and the client's standing mandate is qualitative
    ("aggressive, double-digit growth, little new capital"), not a dated
    dollar figure to measure progress against."""
    return None


def read(summary: PortfolioSummary, reports: list[StockReport],
         risk: RiskMetrics, alerts: list[PortfolioAlert]) -> dict:
    """Assemble the grounded facts + posture. Deterministic, no Claude/scan."""
    from . import journal, plan as plan_service

    plan = plan_service.build_plan()
    ready = plan.get("ready") or []
    ready_moves = [str(m.get("text") or "").strip() for m in ready if m.get("text")]
    critical = [a for a in alerts if getattr(a, "severity", "") == "critical"]
    posture = "act" if (ready or critical) else "hold"

    above, total = _above_trend(reports)
    resil = _resilience(reports)
    goal = _goal()
    realized = journal.realized_total()
    flagged = [f"{a.symbol} — {a.label}" for a in critical]

    value = summary.total_market_value or 0
    metrics = {
        "value": round(value),
        "day_pct": round(summary.day_change_pct, 2),
        "total_return_pct": round(getattr(summary, "total_return_pct", 0) or 0, 1),
        "unrealized_pct": round(summary.total_unrealized_pl_pct, 1),
        "above_trend": above,
        "holdings": total,
        "resilience": resil,
        "realized": round(realized, 2),
        "ready_count": len(ready),
        "ready_moves": ready_moves,
        "critical_count": len(critical),
        "flagged": flagged,
    }
    if goal and value:
        remaining = max(0.0, goal["target"] - value)
        metrics["goal"] = {
            "target": round(goal["target"]),
            "progress_pct": round(value / goal["target"] * 100, 1),
            "remaining": round(remaining),
            "horizon": goal["horizon"],
        }

    # Deterministic grounded reasons — the shown fallback when Claude is down,
    # and the fact base the narration must stick to.
    reasons: list[str] = []
    if posture == "hold":
        if total:
            reasons.append(
                f"{above} of your {total} holdings are still in a healthy "
                f"uptrend — the thesis is intact.")
        reasons.append(
            "Nothing in your plan needs action today and no warning has fired.")
        if metrics.get("goal"):
            gm = metrics["goal"]
            hz = f" by {gm['horizon']}" if gm["horizon"] else ""
            reasons.append(
                f"You're {gm['progress_pct']:.0f}% of the way to your "
                f"${gm['target']:,.0f} goal{hz} — ${gm['remaining']:,.0f} to go, "
                f"with time on your side.")
        if resil:
            reasons.append(
                f"You held {resil['symbol']} from ${resil['low']:,.2f} back to "
                f"${resil['price']:,.2f} (+{resil['gain_pct']:.0f}%) — that "
                f"patience is your edge.")
        if realized > 0:
            reasons.append(
                f"You've already booked ${realized:,.0f} in realized gains by "
                f"staying disciplined.")
        headline = "Hold the course. Nothing changed this week."
        closer = ("A quiet week is the plan working. Stay put — I'll shout the "
                  "moment something real changes.")
    else:
        n = len(ready)
        nc = len(critical)
        if n:
            reasons.append(
                f"{n} move{'s' if n != 1 else ''} in your plan below "
                f"{'are' if n != 1 else 'is'} ready — handle "
                f"{'those' if n != 1 else 'it'}, then it's back to patience.")
        if nc:
            named = "; ".join(flagged[:3])
            reasons.append(
                f"{named} — see 'Needs your attention' below." if named
                else f"{nc} alert{'s' if nc != 1 else ''} need your eyes below.")
        if total:
            reasons.append(
                f"The rest of your book ({above} of {total} still trending up) "
                f"stays exactly where it is.")
        if n and nc:
            headline = "A move and an alert need you — then hold the rest."
        elif n:
            headline = ("A move needs you — then hold." if n == 1
                        else "A couple of moves need you — then hold.")
        else:
            headline = "One thing needs a look — the rest holds."
        closer = "Handle what's flagged, then let the rest compound."

    return {
        "posture": posture,
        "headline": headline,
        "reasons": reasons,
        "closer": closer,
        "metrics": metrics,
    }
