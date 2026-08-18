"""Overnight desk pre-load — the debate, ready before you open the app.

WHY THIS IS NOT "RUN IT ON EVERYTHING"
--------------------------------------
One desk session measured at 9 CLI calls, 394,307 tokens and 62 seconds. Across
seventeen holdings that is ~6.7M tokens and 153 calls a night. The dollars are
notional on a subscription, but the rate limit is not: that volume would throttle
the morning brief, the close recap, the advisor dock and the book, and this app
has already lost a whole day's close recap to exactly that.

So it runs a SMALL number of names, chosen by what actually changed. A debate on
a name where nothing happened re-litigates a settled question at full price. The
scoring below is entirely about "is there something new to say".

Rotation is the second half of the design: a name debated recently is skipped
even if it scores well, so the desk works through the book instead of arguing
about the same two positions every night.
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

# Per night. Four sessions is ~1.6M tokens and ~4 minutes — real but affordable
# against a subscription that also has to run the briefs and the book.
MAX_PER_NIGHT = 4
# Screen candidates judged per night, on top of the holdings above. Five desk
# sessions is ~2M tokens and ~$3.85 — the single most expensive scheduled thing
# in the app, so it is a named number rather than a loop bound.
SCREEN_JUDGED = 5
# Don't re-debate a name inside this window; that's what makes it rotate.
REDEBATE_AFTER_DAYS = 6
# Overnight ET window. After the close so it never competes with market-hours
# work, and finished long before the morning brief needs the CLI at 08:15.
WINDOW_START_MIN = 18 * 60      # 18:00
WINDOW_END_MIN = 23 * 60 + 30   # 23:30

_STATE_FILE = settings.PORTFOLIO_FILE.parent / "nightly_state.json"


def _et_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _load_state() -> dict:
    import json
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(d: dict) -> None:
    import json
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except OSError as exc:
        print(f"[nightly] could not persist state: {exc!r}")


def score_candidates(reports: list, signals: list | None = None) -> list[dict]:
    """Rank holdings by how much NEW there is to argue about.

    Every clause answers "would the desk say something it hasn't already?".
    Freshness is deliberately a weak positive rather than the driver — rotating
    for its own sake burns calls on quiet names.
    """
    from . import debate as debate_service
    from . import stance as stance_service

    sig_syms = {str(s.get("symbol", "")).upper() for s in (signals or [])}
    out: list[dict] = []

    for r in reports:
        sym = r.symbol.upper()
        if not (r.shares or 0):
            continue

        cached = debate_service.get_cached(sym, max_age=10 ** 9)
        age_days = ((time.time() - float(cached["ts"])) / 86400) if cached else 999
        if cached and age_days < REDEBATE_AFTER_DAYS:
            continue                       # argued recently; let it rotate

        score = 0.0
        why: list[str] = []

        # A fired signal is the strongest reason: something happened today.
        if sym in sig_syms:
            score += 40
            why.append("live signal")

        dte = r.days_to_earnings
        if dte is not None and 0 <= dte <= 7:
            score += 35
            why.append(f"earnings in {dte}d")
        elif dte is not None and 8 <= dte <= 14:
            score += 15
            why.append(f"earnings in {dte}d")

        # A big move is new information regardless of direction.
        move = abs(float(r.quote.change_pct or 0))
        if move >= 5:
            score += 25
            why.append(f"moved {r.quote.change_pct:+.1f}% today")
        elif move >= 3:
            score += 12
            why.append(f"moved {r.quote.change_pct:+.1f}% today")

        # A position that has run or broken hard is worth re-examining.
        pl = float(r.unrealized_pl_pct or 0)
        if pl <= -15:
            score += 20
            why.append(f"down {abs(pl):.0f}% on the position")
        elif pl >= 40:
            score += 12
            why.append(f"up {pl:.0f}% on the position")

        # A standing SELL still held is a contradiction worth settling.
        try:
            st = stance_service.get(sym)
            if st and str(st.get("action", "")).upper() in ("SELL", "TRIM"):
                score += 18
                why.append(f"standing {st['action']} but still held")
        except Exception:
            pass

        # Never argued, or argued long ago.
        if not cached:
            score += 10
            why.append("desk has never sat on it")
        elif age_days > 21:
            score += 8
            why.append(f"last debated {age_days:.0f}d ago")

        if score <= 0:
            continue
        out.append({"symbol": sym, "score": round(score, 1),
                    "why": why, "age_days": round(age_days, 1)})

    return sorted(out, key=lambda c: -c["score"])


def screen_and_judge(limit: int = SCREEN_JUDGED) -> list[dict]:
    """Run the low-float screen, then convene the desk on its best candidates.

    Ranked by float turnover — volume over float — because that is the number
    the screen exists to find: how much of the tradeable supply changed hands.
    A name is only worth a 394k-token debate if the supply actually moved.

    These are strangers, not holdings, so the desk is doing real work: deciding
    whether an unfamiliar name deserves attention at all.
    """
    from . import debate as debate_service
    from . import lowfloat

    try:
        out = lowfloat.screen(force=True)
    except Exception as exc:
        print(f"[nightly] screen failed: {exc!r}")
        return []

    results = out.get("results") or []
    print(f"[nightly] screen: {len(results)} passed of "
          f"{out.get('scanned')} scanned ({out.get('coverage_pct')}% coverage)")

    judged: list[dict] = []
    for cand in results[:limit]:
        sym = cand["symbol"]
        try:
            d = debate_service.convene(sym, force=True) or {}
            judged.append({
                "symbol": sym, "price": cand["price"],
                "change_pct": cand["change_pct"], "rvol": cand["rvol"],
                "float_shares": cand.get("float_shares"),
                "float_turnover": cand.get("float_turnover"),
                "verdict": d.get("verdict"), "action": d.get("action"),
                "headline": d.get("headline"), "ts": d.get("ts"),
            })
        except Exception as exc:
            print(f"[nightly] {sym} screen-debate failed: {exc!r}")
    return judged


def maybe_run(force: bool = False) -> dict | None:
    """Pre-load the desk overnight. Called from the watchdog heartbeat."""
    et = _et_now()
    today = et.strftime("%Y-%m-%d")
    state = _load_state()

    if not force:
        mins = et.hour * 60 + et.minute
        if not (WINDOW_START_MIN <= mins < WINDOW_END_MIN):
            return None
        if state.get("last_run") == today:
            return None
        if et.weekday() >= 5:
            return None            # nothing changed over the weekend

    from . import conviction as conviction_service
    from . import debate as debate_service
    from . import portfolio as pf_service

    try:
        _, reports = pf_service.portfolio_summary()
    except Exception as exc:
        print(f"[nightly] could not read the book: {exc!r}")
        return None

    # Never debate off mock prices — the whole session would be reasoning about
    # numbers that were generated rather than observed.
    reports = [r for r in reports if getattr(r.quote, "source", "") == "live"]

    try:
        signals = conviction_service.scan()
    except Exception:
        signals = []

    ranked = score_candidates(reports, signals)[:MAX_PER_NIGHT]
    if not ranked:
        state["last_run"] = today
        state["last_result"] = {"date": today, "ran": [], "note": "nothing new to argue"}
        _save_state(state)
        return {"ran": [], "note": "nothing new to argue"}

    done: list[dict] = []
    for c in ranked:
        try:
            result = debate_service.convene(c["symbol"], force=True) or {}
            # verdict/action/headline are flat STRINGS on the debate result.
            # Treating verdict as a nested object cost four completed debates
            # their summary row — the transcripts were cached fine, but the
            # night reported "0 sessions" because the recording step threw.
            done.append({
                "symbol": c["symbol"], "score": c["score"], "why": c["why"],
                "verdict": result.get("verdict"),
                "action": result.get("action"),
                "headline": result.get("headline"),
                "ts": result.get("ts"),
            })
        except Exception as exc:
            print(f"[nightly] {c['symbol']} debate failed: {exc!r}")

    # Then the screen: fresh names nobody in the book has looked at.
    screened: list[dict] = []
    try:
        screened = screen_and_judge()
    except Exception as exc:
        print(f"[nightly] screen stage failed: {exc!r}")

    state["last_run"] = today
    state["last_result"] = {"date": today, "ran": done, "screened": screened}
    _save_state(state)

    if done or screened:
        try:
            from . import push
            # Name the symbols and their rulings. A bare count would be exactly
            # the notification that gets muted.
            parts = [f"{d['symbol']} {d['action'] or d['verdict'] or '—'}"
                     for d in done + screened]
            push.send("DESK SAT OVERNIGHT", f"Ready to review: {'; '.join(parts)}",
                      data={"type": "nightly_debate"})
        except Exception as exc:
            print(f"[nightly] push failed: {exc!r}")

    return {"ran": done, "screened": screened}


def last_result() -> dict:
    """What the desk did last night, for the morning review."""
    return _load_state().get("last_result") or {"ran": []}
