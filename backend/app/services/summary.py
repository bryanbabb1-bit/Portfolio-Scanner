"""Daily briefs — a pre-market 'what to watch today' and an end-of-day recap.

The noise that doesn't warrant a real-time push (analysis, holds, extended
runners, low-conviction ideas) rolls into two digests a day instead of buzzing
the phone all day. Fired once each from the poll-driven scan (no scheduler):
morning ~8:15-10:00 ET, close recap ~16:00-17:30 ET, weekdays only.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

_STATE_FILE = settings.PORTFOLIO_FILE.parent / "summary_state.json"
_BRIEF_FILE = settings.PORTFOLIO_FILE.parent / "daily_brief.json"


def _et_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _load(path, default):
    # UTF-8 to match _save (dashes, ≤, etc.); cp1252 fallback for legacy files.
    # Reading a UTF-8 file with the Windows default codec is what turned
    # em-dashes into "â€"" gibberish in the briefs.
    for enc in ("utf-8", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return default


def _save(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def latest() -> dict | None:
    """The most recent brief, for the dashboard card + notification tap."""
    return _load(_BRIEF_FILE, None)


def _brief_id(b: dict) -> str:
    return f"{b.get('type')}:{b.get('generated_at')}"


def latest_state() -> dict:
    """The latest brief plus whether it's been dismissed. A NEW brief (next
    morning/close) has a fresh id, so it comes back automatically."""
    b = latest()
    if not b:
        return {"brief": None, "dismissed": False}
    state = _load(_STATE_FILE, {})
    return {"brief": b, "dismissed": state.get("dismissed_brief") == _brief_id(b)}


def dismiss() -> dict:
    """Mark the current brief read — it hides until the next one posts."""
    b = latest()
    if not b:
        return {"dismissed": None}
    state = _load(_STATE_FILE, {})
    state["dismissed_brief"] = _brief_id(b)
    _save(_STATE_FILE, state)
    return {"dismissed": _brief_id(b)}


# A scheduled brief gets a few shots inside its window before it settles for a
# fallback. The advisor is a local CLI invocation and it can hiccup transiently:
# on 2026-07-29 the 16:00 recap drew "Advisor unavailable — here is the raw
# setup", and because the day was stamped on that fallback the window closed with
# no real recap at all and a push whose entire body read "Today's close recap".
# The same build succeeded on the next attempt, so one hiccup should cost one
# heartbeat (~2 min), not the day.
MAX_ADVISOR_ATTEMPTS = 4


def _run_due(kind: str, state: dict, today: str) -> dict | None:
    """Run one scheduled brief, retrying a failed advisor call in-window.

    The day is stamped only once the advisor actually answered, or once the
    attempts are spent — so a transient failure doesn't burn the slot, and a
    genuine outage still delivers something rather than going silent.
    """
    brief = build(kind)
    # Attempts are date-stamped so a count left behind by a crash can't suppress
    # tomorrow's retries.
    prior = str(state.get(f"{kind}_tries") or "")
    tries = (int(prior.split(":")[1]) if prior.startswith(f"{today}:") else 0) + 1

    if brief.get("engine") == "claude" or tries >= MAX_ADVISOR_ATTEMPTS:
        _emit(brief)
        state[kind] = today
        state.pop(f"{kind}_tries", None)
        _save(_STATE_FILE, state)
        return brief

    # Hold the slot open for the next heartbeat instead of spending the window on
    # a brief that has no advisor read in it.
    state[f"{kind}_tries"] = f"{today}:{tries}"
    _save(_STATE_FILE, state)
    print(f"[summary] {kind} brief: advisor unavailable, "
          f"attempt {tries}/{MAX_ADVISOR_ATTEMPTS} — retrying next heartbeat")
    return None


def maybe_send_daily(force_kind: str | None = None) -> dict | None:
    """Emit the morning brief or close recap if due (once per day each)."""
    if force_kind:
        brief = build(force_kind)
        _emit(brief)
        return brief
    et = _et_now()
    if et.weekday() >= 5:
        return None
    today = et.strftime("%Y-%m-%d")
    mins = et.hour * 60 + et.minute
    state = _load(_STATE_FILE, {})
    if 8 * 60 + 15 <= mins < 10 * 60 and state.get("morning") != today:
        return _run_due("morning", state, today)
    if 16 * 60 <= mins < 17 * 60 + 30 and state.get("eod") != today:
        return _run_due("eod", state, today)
    return None


# ---------------------------------------------------------------- facts
def _facts(kind: str) -> str:
    from . import portfolio as pf, watchpoints as wp
    lines: list[str] = []
    try:
        summary, reports = pf.portfolio_summary()
        lines.append(
            f"Book ${summary.total_market_value:,.0f} "
            f"({summary.day_change_pct:+.2f}% today), cash ${summary.cash:,.0f}.")
        held = sorted((r for r in reports if r.market_value),
                      key=lambda r: r.market_value or 0, reverse=True)
        for r in held[:6]:
            earn = (f", EARNINGS in {r.days_to_earnings}d"
                    if r.days_to_earnings is not None and r.days_to_earnings <= 6 else "")
            lines.append(
                f"  {r.symbol}: ${r.quote.price} ({r.quote.change_pct:+.1f}% today), "
                f"P/L {r.unrealized_pl_pct:+.1f}%, RSI {r.indicators.rsi}{earn}")
        price_rsi = {r.symbol: (r.quote.price, r.indicators.rsi) for r in reports}
    except Exception:
        price_rsi = {}
    # Armed triggers (the client's own action levels) + distance to firing.
    try:
        armed = [w for w in wp.list_watchpoints(include_triggered=False)]
        if armed:
            lines.append("Armed triggers (yours):")
            for w in armed[:10]:
                pr = price_rsi.get(w["symbol"])
                dist = ""
                if pr:
                    cur = pr[1] if w["kind"].startswith("rsi") else pr[0]
                    if cur is not None:
                        gap = w["level"] - cur
                        dist = f" (now {cur:g}, {gap:+g} to trigger)"
                lines.append(f"  {w['symbol']} {wp.condition_str(w)}{dist} — {w.get('note','')[:60]}")
    except Exception:
        pass
    # For the recap: what actually fired today.
    if kind == "eod":
        try:
            notes = _load(settings.PORTFOLIO_FILE.parent / "conviction_notes.json", {})
            today = _et_now().strftime("%Y-%m-%d")
            fired = [v for v in notes.values()
                     if str(v.get("generated_at", "")).startswith(today)]
            if fired:
                lines.append("Signals that fired today:")
                for v in fired[:12]:
                    lines.append(f"  {v.get('symbol')} [{v.get('rule')}] "
                                 f"{v.get('action', '')} — {v.get('headline', '')[:60]}")
        except Exception:
            pass
    # A little market context both ways.
    try:
        from . import runner
        movers = runner.live_movers()[:6]
        if movers:
            lines.append("Notable market movers now: " + ", ".join(
                f"{m['symbol']} {m['change_pct']:+.0f}%" for m in movers))
    except Exception:
        pass
    return "\n".join(lines)


_MORNING_FMT = (
    'Respond with ONLY JSON: {"headline": under-10-word hook, "summary": 1-2 '
    'sentence set-up for the day, "watch": array of 4-8 TERSE bullets — each a '
    'specific thing to watch today with its level/trigger (e.g. "GEV: buy '
    'trigger $1090, ~3% below — wait for it", "IREN reports Thu — trim risk '
    'into it"). No fluff.}'
)
_EOD_FMT = (
    'Respond with ONLY JSON: {"headline": under-10-word hook, "summary": 1-2 '
    'sentence read on the day, "recap": array of 3-6 bullets — what happened '
    '(book move, what fired, notable positions), "watch": array of 3-6 bullets '
    '— what to watch TOMORROW with levels/triggers.}'
)


def build(kind: str) -> dict:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    date = _et_now().strftime("%Y-%m-%d")
    facts = _facts(kind)

    def _fallback() -> dict:
        return {
            "type": kind, "date": date, "generated_at": stamp, "engine": "fallback",
            "headline": ("What to watch today" if kind == "morning"
                         else "Today's close recap"),
            "summary": "Advisor unavailable — here is the raw setup.",
            "watch": [ln.strip() for ln in facts.splitlines() if ln.strip()][:8],
            "recap": [],
        }

    if not settings.ADVISOR_ENABLED:
        return _fallback()

    from . import advisor
    if kind == "morning":
        role = ("You are the client's watchdog advisor writing the PRE-MARKET "
                "brief — 'what to look out for today'. Their armed triggers will "
                "push automatically the moment they fire; this is the heads-up so "
                "they know what's in play. Be specific and scannable.")
        fmt = _MORNING_FMT
    else:
        role = ("You are the client's watchdog advisor writing the END-OF-DAY "
                "recap — what happened today and what to watch tomorrow. Be "
                "specific and scannable; acknowledge the day honestly.")
        fmt = _EOD_FMT
    prompt = f"{advisor._PERSONA}\n\n{role}\n\nThe client's data:\n{facts}\n\n{fmt}"
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return _fallback()
    out = _fallback()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        try:
            obj = json.loads(raw[s:e + 1])
            out = {
                "type": kind, "date": date, "generated_at": stamp, "engine": "claude",
                "headline": str(obj.get("headline") or out["headline"]),
                "summary": str(obj.get("summary") or ""),
                "watch": advisor._as_bullets(obj.get("watch")),
                "recap": advisor._as_bullets(obj.get("recap")) if kind == "eod" else [],
            }
        except json.JSONDecodeError:
            pass
    return out


def _emit(brief: dict) -> None:
    _save(_BRIEF_FILE, brief)
    try:
        from . import push
        title = ("MORNING BRIEF" if brief["type"] == "morning" else "CLOSE RECAP")
        body = brief.get("headline") or "Your daily brief is ready."
        # A fallback brief has no advisor read in it, so say that outright rather
        # than pushing a label that looks like a normal brief and isn't.
        if brief.get("engine") != "claude":
            body = f"Couldn't reach the advisor — raw numbers only. {body}"
        push.send(f"▪ {title}", body, sound="default",
                  data={"type": "brief", "kind": brief["type"]})
    except Exception as exc:
        print(f"[summary] push failed: {exc!r}")
