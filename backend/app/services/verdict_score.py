"""Did the desk make the right call? Graded on a trailing 5-day reaction.

WHY THIS EXISTS
---------------
The first screen run returned AVOID five times out of five. That is either a
filter doing its job or a filter with its thumb on the scale, and the two are
indistinguishable from the verdicts alone. The only way to tell is to check what
the names did afterwards and keep score.

HOW A CALL IS GRADED
--------------------
Every ruling is stamped with the price at the time. Five sessions later:

  AVOID / SELL / TRIM   right if the name did NOT run — flat or down
  BUY / ADD             right if it rose meaningfully
  HOLD                  no directional claim, recorded but not graded
  WATCH                 depends on the ruling it came with, see below

WHY WATCH IS NOT AUTOMATICALLY NEUTRAL
--------------------------------------
When the screen moved from ignition setups to reclaim setups the judge stopped
writing AVOID and started writing WATCH, while its VERDICT stayed REJECT on
nine of the first ten names. "REJECT — watch above $8.39, don't buy here" is a
skip call wearing a neutral word: the client was told not to buy, and if the
name then doubles that was a miss.

Grading on the action word alone, every one of those calls fell through the
neutral hole and the scorecard graded nothing — which is exactly the state this
file was written to prevent. So a WATCH is graded as a skip when the verdict was
REJECT, and left ungraded when the verdict was APPROVE (an approved WATCH with
an entry level, "buy only above $16", is a genuine conditional).

The threshold is deliberately asymmetric. Telling someone to skip a stock that
then went up 2% was not a bad call; telling them to skip one that doubled was.
MOVE_PCT is the line where "you missed something" starts being true.

WHAT THIS CANNOT TELL YOU
-------------------------
Five days is a reaction, not an outcome, and a handful of calls is not a sample.
A hit rate over ten rulings is a talking point; over a hundred it starts being
evidence. The count is always reported next to the rate so the difference is
visible.
"""
from __future__ import annotations

import time

from ..config import settings

WINDOW_DAYS = 5
# A move big enough that missing it (or sitting through it) actually mattered.
MOVE_PCT = 10.0

_BEARISH = {"AVOID", "SELL", "TRIM"}
_BULLISH = {"BUY", "ADD"}
_NEUTRAL = {"HOLD"}
# Means "skip it" or "not yet" depending on the verdict beside it — resolved in
# grade_one rather than assumed here.
_CONDITIONAL = {"WATCH"}


def _price_now(symbol: str) -> tuple[float | None, str]:
    from . import market_data
    try:
        md = market_data.get_market_data(symbol)
        if md.source != "live" or md.history is None or md.history.empty:
            return None, md.source
        return float(md.history["Close"].iloc[-1]), "live"
    except Exception as exc:
        print(f"[verdict] price for {symbol} failed: {exc!r}")
        return None, "error"


def grade_one(action: str, price_then: float, price_now: float,
              verdict: str | None = None) -> dict:
    """Grade a single call. Returns verdict-was-right plus the move.

    `verdict` disambiguates WATCH: with a REJECT beside it the client was told
    not to buy, so it grades as a skip; with an APPROVE it is a real "wait for
    the level" and stays ungraded.
    """
    move = (price_now / price_then - 1) * 100 if price_then else 0.0
    act = (action or "").upper()
    ver = (verdict or "").upper()
    if act in _CONDITIONAL:
        act = "AVOID" if ver == "REJECT" else ""
    if act in _NEUTRAL or not act:
        return {"move_pct": round(move, 2), "graded": False, "right": None,
                "note": "no directional call to grade"}
    if act in _BEARISH:
        # A skip is wrong only if the thing then ran away from you.
        right = move < MOVE_PCT
        note = (f"skipped and it ran +{move:.0f}%" if not right
                else f"skipped and it went {move:+.0f}%")
    elif act in _BULLISH:
        right = move >= MOVE_PCT
        note = (f"called it and it ran {move:+.0f}%" if right
                else f"called it and it only went {move:+.0f}%")
    else:
        return {"move_pct": round(move, 2), "graded": False, "right": None,
                "note": f"unrecognised action {act}"}
    return {"move_pct": round(move, 2), "graded": True, "right": right,
            "graded_as": act, "note": note}


def scorecard(days: int = 30) -> dict:
    """Grade every ruling old enough to have a trailing reaction."""
    from . import debate as debate_service

    cutoff = time.time() - days * 86400
    ripe_after = WINDOW_DAYS * 86400
    rows: list[dict] = []

    for d in debate_service.history(limit=200):
        ts = float(d.get("ts") or 0)
        if ts < cutoff:
            continue
        age_days = (time.time() - ts) / 86400
        sym = d.get("symbol")
        price_then = d.get("price")
        if not sym or not price_then:
            continue

        row = {
            "symbol": sym, "action": d.get("action"),
            "verdict": d.get("verdict"), "headline": d.get("headline"),
            "ts": ts, "age_days": round(age_days, 1),
            "price_then": price_then,
        }
        if time.time() - ts < ripe_after:
            # Too young to judge. Shown, not scored — a call still in flight is
            # not a call that was wrong.
            row.update(pending=True, graded=False, right=None,
                       note=f"{WINDOW_DAYS - int(age_days)}d until it can be graded")
            rows.append(row)
            continue

        now, src = _price_now(sym)
        if now is None:
            row.update(pending=False, graded=False, right=None,
                       note=f"no live price ({src})")
            rows.append(row)
            continue
        row.update(price_now=round(now, 2), pending=False,
                   **grade_one(d.get("action"), float(price_then), now,
                               d.get("verdict")))
        rows.append(row)

    graded = [r for r in rows if r.get("graded")]
    hits = [r for r in graded if r.get("right")]
    by_action: dict[str, dict] = {}
    for r in graded:
        # Keyed on what it was graded AS, so a REJECT/WATCH lands in the same
        # bucket as an AVOID instead of inventing a "WATCH hit rate".
        a = (r.get("graded_as") or r.get("action") or "?").upper()
        b = by_action.setdefault(a, {"n": 0, "right": 0})
        b["n"] += 1
        b["right"] += 1 if r["right"] else 0
    for a, b in by_action.items():
        b["hit_rate"] = round(b["right"] / b["n"] * 100, 1) if b["n"] else None

    return {
        "window_days": WINDOW_DAYS,
        "move_threshold_pct": MOVE_PCT,
        "graded": len(graded),
        "pending": sum(1 for r in rows if r.get("pending")),
        "hit_rate": round(len(hits) / len(graded) * 100, 1) if graded else None,
        "by_action": by_action,
        # The number that decides whether the hit rate means anything.
        "confidence": ("too few calls to mean anything" if len(graded) < 10
                       else "indicative, not evidence" if len(graded) < 40
                       else "starting to be evidence"),
        "rows": sorted(rows, key=lambda r: -r["ts"]),
    }
