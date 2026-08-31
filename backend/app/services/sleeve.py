"""The trading sleeve — a second book with its own capital, its own rules, and
a ticket for every idea.

WHY A SECOND BOOK
-----------------
The core book is eleven compounders held under a rulebook that beat every
model we built (buy-and-hold, accumulate on weakness, never sell a conviction
on a technical break). That rulebook is correct for the core and fatal for a
trade: it has no exits, it sizes to conviction, and its advisor is written to
resist selling anything. Every aggressive idea has been forced to argue with a
core position for the same dollar, and the core has won every time. So the
runner engine spent a month issuing "do not chase" warnings and a week
switched off entirely.

The sleeve fixes that structurally rather than by asking the same brain to be
two people. It has a stated capital allocation, hard stops on everything, risk
sizing from the study that found concentration is the lever (ab4a387: 1 slot at
8% risk was the only configuration to beat SPY in both halves of 15 years),
and a deterministic lifecycle for every idea:

    armed  -> issued with entry, stop, target, size; expires at the close
    live   -> Bryan confirms the fill (never managed on a guess)
    exit   -> the manager says SELL (stop / trail / target / time); one push
    closed -> Bryan confirms the exit; graded in R; feeds the scorecard

Detection and sizing cost zero CLI calls. The model may write a "why"; a
ticket never waits on it.

WHAT THE EVIDENCE PERMITS (backend/studies, scorecard)
-------------------------------------------------------
Chasing +50% movers into the close lost money in 8 of 8 variants — the sleeve
never tickets an extended name. Igniting names (7-25% on 3x volume, near the
high) graded +5.5% average across the six live buy-side alerts that fired
before the engine was gated off. Six is not proof; the sleeve grades every
ticket in R with the sample size on screen so the number earns trust or loses
it in public.
"""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "sleeve.json"
_lock = threading.RLock()

# ------------------------------------------------------------------ config
# Everything here is editable from Settings; these are the desk's defaults.
DEFAULTS: dict = {
    "enabled": True,
    # Capital. A percentage of the core book's live value, or an explicit
    # dollar figure that wins when set. Tickets size against this from day
    # one even before the money moves; the blotter says how much is funded.
    "capital_pct": 15.0,
    "capital_usd": None,
    # Risk per ticket as a percentage of sleeve equity. The sizing study put
    # Kelly at ~17% on the pullback edge and 5-8% as the range that beat the
    # index out of sample; 1% (the core's setting) is one-eighth of that.
    "risk_pct": 5.0,
    "max_slots": 2,
    "max_tickets_per_day": 3,
    # Ignition (runner) parameters. Lottery sizing: a runner is capped at a
    # fraction of the sleeve regardless of the risk math, because the stop on
    # a thin name is a hope, not a guarantee.
    "ignition_stop_pct": 0.18,
    "ignition_max_pct": 0.25,
    "ignition_time_stop_sessions": 3,
    # Pullback (the t=2.48 edge). Stop is volatility-based — 2.5 ATR is what
    # the 5-year replay used, wide enough to survive normal noise across days.
    "pullback_atr_stop": 2.5,
    "pullback_max_hold_sessions": 20,
    # Footprint. Never bought on the volume alone: at 8x the median 5-day
    # return is -8%, so the ticket WAITS above the prior day's high and dies
    # unfilled if the break never comes.
    "footprint_watch_sessions": 5,
    "footprint_stop_pct": 0.12,
    # Exits shared by every engine.
    "trail_pct": 0.25,      # trail off the high-water mark once the trade is +1R
    "target_r": 3.0,
}

ENGINES = ("ignition", "pullback", "footprint", "manual")

# What a ticket can be, in order: a conditional watch that has not triggered,
# an order waiting on a fill, a position, an exit awaiting confirmation, done.
OPEN_STATUSES = ("watching", "armed", "live", "exit")


def _et_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


# ------------------------------------------------------------------ store
def _empty() -> dict:
    return {"config": {}, "tickets": [], "equity_history": [], "last_mark": None}


def load() -> dict:
    with _lock:
        try:
            with open(_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return _empty()
            for k, v in _empty().items():
                d.setdefault(k, v)
            return d
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return _empty()


def save(book: dict) -> None:
    with _lock:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(book, f, indent=2, ensure_ascii=False)


def config(book: dict | None = None) -> dict:
    book = book or load()
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (book.get("config") or {}).items() if k in DEFAULTS})
    return cfg


def set_config(changes: dict) -> dict:
    """Persist edited sleeve settings. Unknown keys are ignored, and the
    numbers are clamped to ranges that cannot produce a nonsense ticket."""
    with _lock:
        book = load()
        cfg = dict(book.get("config") or {})
        for k, v in (changes or {}).items():
            if k not in DEFAULTS:
                continue
            if k == "enabled":
                cfg[k] = bool(v)
            elif k == "capital_usd":
                cfg[k] = None if v in (None, "", 0) else max(0.0, float(v))
            elif k in ("max_slots", "max_tickets_per_day", "ignition_time_stop_sessions",
                       "pullback_max_hold_sessions", "footprint_watch_sessions"):
                cfg[k] = int(max(1, min(20, int(v))))
            elif k == "capital_pct":
                cfg[k] = float(max(0.0, min(100.0, float(v))))
            elif k == "risk_pct":
                cfg[k] = float(max(0.5, min(25.0, float(v))))
            elif k == "pullback_atr_stop":
                cfg[k] = float(max(0.5, min(6.0, float(v))))
            elif k in ("ignition_stop_pct", "ignition_max_pct", "trail_pct",
                       "footprint_stop_pct"):
                cfg[k] = float(max(0.03, min(0.60, float(v))))
            elif k == "target_r":
                cfg[k] = float(max(1.0, min(10.0, float(v))))
        book["config"] = cfg
        save(book)
        return config(book)


def enabled() -> bool:
    try:
        return bool(config().get("enabled", True))
    except Exception:
        return False


# ----------------------------------------------------------------- capital
def _core_book_value() -> float:
    try:
        from . import portfolio as pf_service
        summary, _ = pf_service.portfolio_summary()
        return float(summary.total_market_value or 0.0)
    except Exception:
        return 0.0


def capital(cfg: dict | None = None, core_value: float | None = None) -> float:
    """What Bryan has allotted to the sleeve. Explicit dollars win; else a
    percentage of the live core book."""
    cfg = cfg or config()
    if cfg.get("capital_usd"):
        return round(float(cfg["capital_usd"]), 2)
    base = _core_book_value() if core_value is None else core_value
    return round(base * float(cfg.get("capital_pct") or 0) / 100.0, 2)


def realized_pnl(book: dict) -> float:
    return round(sum(float(t.get("pnl_usd") or 0) for t in book["tickets"]
                     if t.get("status") == "closed"), 2)


def equity(book: dict, quotes: dict | None = None, cap: float | None = None) -> float:
    """Capital plus everything the tickets have earned or are earning."""
    cap = capital() if cap is None else cap
    unreal = 0.0
    for t in book["tickets"]:
        if t.get("status") in ("live", "exit") and t.get("fill_price"):
            q = (quotes or {}).get(t["symbol"])
            px = float(q["price"]) if q and q.get("price") else float(t.get("last_price") or t["fill_price"])
            unreal += (px - float(t["fill_price"])) * float(t["shares"])
    return round(cap + realized_pnl(book) + unreal, 2)


# ------------------------------------------------------------------ sizing
def size(entry: float, stop: float, eq: float, engine: str, cfg: dict) -> dict:
    """Risk-based size: shares = risk dollars / stop distance, then capped.

    A wide stop buys a smaller position — that is the whole point. Runners
    carry a second cap (a fraction of the sleeve) because on a thin float the
    stop is a hope; the cap is what actually bounds the damage."""
    if entry <= 0 or stop <= 0 or stop >= entry or eq <= 0:
        return {"shares": 0.0, "notional": 0.0, "risk_usd": 0.0, "r_unit": 0.0}
    r_unit = entry - stop
    risk_usd = eq * float(cfg["risk_pct"]) / 100.0
    notional = risk_usd / r_unit * entry
    cap = eq / max(1, int(cfg["max_slots"]))
    if engine == "ignition":
        cap = min(cap, eq * float(cfg["ignition_max_pct"]))
    notional = min(notional, cap)
    shares = notional / entry
    return {
        "shares": round(shares, 4),
        "notional": round(shares * entry, 2),
        "risk_usd": round(shares * r_unit, 2),
        "r_unit": round(r_unit, 4),
    }


# ----------------------------------------------------------------- helpers
def _today() -> str:
    return _et_now().strftime("%Y-%m-%d")


def _session_close_ts(now: datetime | None = None) -> float:
    """When an armed ticket dies: 16:00 ET today, or the next weekday's close
    if the session has already ended (an after-hours ignition is a ticket for
    tomorrow's open, not one that expires before it is read)."""
    from datetime import timedelta
    now = now or _et_now()
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    while now > close or close.weekday() >= 5:
        close = close + timedelta(days=1)
    return close.timestamp()


def _open_for(book: dict, symbol: str) -> dict | None:
    """Any live commitment to this name — including a conditional watch, so a
    second engine cannot stack a duplicate ticket on the same symbol."""
    for t in book["tickets"]:
        if t["symbol"] == symbol and t.get("status") in OPEN_STATUSES:
            return t
    return None


def _issued_today(book: dict) -> int:
    today = _today()
    return sum(1 for t in book["tickets"]
               if str(t.get("created", ""))[:10] == today and t.get("engine") != "manual")


def _slots_used(book: dict) -> int:
    return sum(1 for t in book["tickets"] if t.get("status") in ("live", "exit"))


def _notify(title: str, body: str, sound: str, data: dict) -> None:
    """One choke point for pushes so tests can record instead of send."""
    try:
        from . import push
        push.send(title, body, data=data, sound=sound)
    except Exception as exc:
        print(f"[sleeve] push failed: {exc!r}")


def _money(v: float) -> str:
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


# ------------------------------------------------------------------ tickets
def issue(symbol: str, engine: str, entry: float, stop: float, *,
          target: float | None = None, why: list[str] | None = None,
          headline: str = "", meta: dict | None = None, push_it: bool = True,
          book: dict | None = None, eq: float | None = None,
          expires_ts: float | None = None,
          trigger_above: float | None = None) -> dict | None:
    """Create a ticket. Returns None when the desk refuses: disabled,
    duplicate, daily cap, bad levels, or nothing to size against.

    trigger_above turns it into a conditional WATCH: it holds no money and
    makes no noise until price trades through that level, at which point it
    is re-sized at the trigger and armed. That is the only honest way to take
    a footprint name — the volume says something is happening, the break says
    it is happening in the direction you want."""
    with _lock:
        own_book = book is None
        book = book or load()
        cfg = config(book)
        sym = symbol.upper().strip()
        if not cfg.get("enabled", True) or engine not in ENGINES:
            return None
        if _open_for(book, sym):
            return None
        if engine != "manual" and _issued_today(book) >= int(cfg["max_tickets_per_day"]):
            return None
        eq = equity(book) if eq is None else eq
        sz = size(entry, stop, eq, engine, cfg)
        if sz["shares"] <= 0:
            return None
        if target is None:
            target = entry + float(cfg["target_r"]) * sz["r_unit"]
        now = time.time()
        stamp = _et_now().strftime("%Y%m%d%H%M%S")
        t = {
            "id": f"tk_{stamp}_{sym}",
            "symbol": sym, "engine": engine, "side": "buy",
            "status": "watching" if trigger_above else "armed",
            "trigger_above": round(float(trigger_above), 4) if trigger_above else None,
            "created": _et_now().strftime("%Y-%m-%d %H:%M:%S"), "ts": now,
            "expires": expires_ts if expires_ts is not None else _session_close_ts(),
            "entry": round(float(entry), 4), "stop": round(float(stop), 4),
            "target": round(float(target), 4),
            "shares": sz["shares"], "notional": sz["notional"],
            "risk_usd": sz["risk_usd"], "r_unit": sz["r_unit"],
            "sleeve_equity": round(eq, 2),
            "why": list(why or [])[:4], "headline": headline or "",
            "note": "", "note_risk": "", "note_engine": "",
            "meta": meta or {},
            "fill_price": None, "fill_ts": None, "high_water": None,
            "current_stop": None, "trail_armed": False,
            "exit_signal": None, "exit_price": None, "exit_ts": None,
            "exit_reason": None, "r_multiple": None, "pnl_usd": None,
            "last_price": round(float(entry), 4), "sessions_held": 0,
        }
        book["tickets"].append(t)
        if own_book:
            save(book)
        if push_it and not trigger_above:
            stop_pct = (t["stop"] / t["entry"] - 1) * 100
            tgt_r = (t["target"] - t["entry"]) / t["r_unit"] if t["r_unit"] else 0
            _notify(
                f"BUY {sym} {_money(t['notional'])} @ {t['entry']:.2f}",
                f"{engine.title()} · stop {t['stop']:.2f} ({stop_pct:.0f}%) · "
                f"target {t['target']:.2f} (+{tgt_r:.1f}R) · risk {_money(t['risk_usd'])}"
                + (f" · {headline}" if headline else "") + " · expires at the close",
                sound="runner.wav" if engine == "ignition" else "buy.wav",
                data={"type": "ticket", "id": t["id"], "symbol": sym},
            )
        return t


def get(ticket_id: str, book: dict | None = None) -> dict | None:
    book = book or load()
    return next((t for t in book["tickets"] if t["id"] == ticket_id), None)


def confirm_fill(ticket_id: str, price: float, shares: float | None = None) -> dict:
    """Bryan filled it. The ticket goes LIVE at HIS price, and the stop keeps
    its planned distance from the actual fill — a fill 3% above the reference
    price must not silently tighten the stop to nothing."""
    with _lock:
        book = load()
        t = get(ticket_id, book)
        if not t:
            raise KeyError(ticket_id)
        if t["status"] != "armed":
            raise ValueError(f"ticket is {t['status']}, not armed")
        price = float(price)
        if price <= 0:
            raise ValueError("fill price must be positive")
        planned_dist = t["entry"] - t["stop"]
        t["fill_price"] = round(price, 4)
        t["fill_ts"] = time.time()
        t["fill_day"] = _today()
        if shares and float(shares) > 0:
            t["shares"] = round(float(shares), 4)
        t["notional"] = round(t["shares"] * price, 2)
        t["stop"] = round(price - planned_dist, 4)
        t["current_stop"] = t["stop"]
        t["r_unit"] = round(planned_dist, 4)
        t["risk_usd"] = round(t["shares"] * planned_dist, 2)
        t["target"] = round(price + (t["target"] - t["entry"]), 4)
        t["high_water"] = round(price, 4)
        t["last_price"] = round(price, 4)
        t["status"] = "live"
        save(book)
        return t


def pass_ticket(ticket_id: str) -> dict:
    with _lock:
        book = load()
        t = get(ticket_id, book)
        if not t:
            raise KeyError(ticket_id)
        if t["status"] != "armed":
            raise ValueError(f"ticket is {t['status']}, not armed")
        t["status"] = "passed"
        t["closed_ts"] = time.time()
        save(book)
        return t


def close(ticket_id: str, price: float, reason: str = "manual") -> dict:
    """Bryan sold it (or confirms the exit the manager signalled). Grade in R."""
    with _lock:
        book = load()
        t = get(ticket_id, book)
        if not t:
            raise KeyError(ticket_id)
        if t["status"] not in ("live", "exit"):
            raise ValueError(f"ticket is {t['status']}, not live")
        price = float(price)
        _grade(t, price, reason)
        save(book)
        return t


def _grade(t: dict, price: float, reason: str) -> None:
    t["exit_price"] = round(price, 4)
    t["exit_ts"] = time.time()
    t["exit_reason"] = reason
    t["status"] = "closed"
    t["pnl_usd"] = round((price - t["fill_price"]) * t["shares"], 2)
    t["r_multiple"] = (round((price - t["fill_price"]) / t["r_unit"], 2)
                       if t.get("r_unit") else None)


# --------------------------------------------------------------- lifecycle
def expire(book: dict, now_ts: float | None = None) -> list[str]:
    """Orders that were not filled by the close, and conditional watches whose
    break never came, are gone. Silently — an expiry is not news."""
    now_ts = time.time() if now_ts is None else now_ts
    gone: list[str] = []
    for t in book["tickets"]:
        if t.get("status") in ("armed", "watching") and now_ts >= float(t.get("expires") or 0):
            t["status"] = "expired"
            t["closed_ts"] = now_ts
            gone.append(t["symbol"])
    return gone


def check_triggers(book: dict, quotes: dict, cfg: dict | None = None,
                   eq: float | None = None) -> list[dict]:
    """Conditional watches whose level has traded through become live orders.

    The ticket is RE-SIZED at the trigger, not at the price it was written at:
    the level is the entry, and sizing off a stale price would put on a
    position the stop no longer bounds."""
    cfg = cfg or config(book)
    eq = equity(book) if eq is None else eq
    fired: list[dict] = []
    for t in book["tickets"]:
        if t.get("status") != "watching" or not t.get("trigger_above"):
            continue
        q = quotes.get(t["symbol"])
        if not q or not q.get("price") or q.get("source", "live") != "live":
            continue
        px = float(q["price"])
        t["last_price"] = round(px, 4)
        trigger = float(t["trigger_above"])
        if px < trigger:
            continue
        # Enter at the trigger or the current print, whichever is worse for us —
        # a gap through the level is not a fill at the level.
        entry = max(trigger, px)
        planned_dist = float(t["entry"]) - float(t["stop"])
        stop = entry - planned_dist
        sz = size(entry, stop, eq, t["engine"], cfg)
        if sz["shares"] <= 0:
            continue
        t.update(status="armed", entry=round(entry, 4), stop=round(stop, 4),
                 target=round(entry + float(cfg["target_r"]) * sz["r_unit"], 4),
                 shares=sz["shares"], notional=sz["notional"],
                 risk_usd=sz["risk_usd"], r_unit=sz["r_unit"],
                 sleeve_equity=round(eq, 2), triggered_ts=time.time(),
                 expires=_session_close_ts())
        fired.append({"kind": "triggered", "ticket": t, "price": entry})
    return fired


def manage(book: dict, quotes: dict, cfg: dict | None = None,
           today: str | None = None) -> list[dict]:
    """Work every LIVE ticket against live prices. Returns the events.

    Rules, in order: ratchet the high-water mark; at +1R move the stop to
    breakeven and arm the trail; the trail follows the high-water mark and
    only ever rises; a stop hit, a target hit, or a time stop signals EXIT
    exactly once. The manager never closes a ticket itself — Bryan holds the
    shares, so he confirms the exit and the price he actually got."""
    cfg = cfg or config(book)
    today = today or _today()
    events: list[dict] = []
    for t in book["tickets"]:
        if t.get("status") != "live":
            continue
        q = quotes.get(t["symbol"])
        if not q or not q.get("price"):
            continue
        if q.get("source", "live") != "live":
            continue                        # never manage a real position on fake data
        px = float(q["price"])
        t["last_price"] = round(px, 4)
        fill = float(t["fill_price"])
        r_unit = float(t["r_unit"]) or max(fill * 0.01, 1e-6)
        t["high_water"] = round(max(float(t.get("high_water") or fill), px), 4)
        if today != t.get("fill_day") and t.get("last_session") != today:
            t["sessions_held"] = int(t.get("sessions_held") or 0) + 1
            t["last_session"] = today
        r_now = (px - fill) / r_unit

        # +1R: breakeven and arm the trail.
        if not t.get("trail_armed") and px >= fill + r_unit:
            t["trail_armed"] = True
            new_stop = max(float(t["current_stop"]), fill)
            if new_stop > float(t["current_stop"]):
                t["current_stop"] = round(new_stop, 4)
            events.append({"kind": "trail_armed", "ticket": t, "price": px, "r": r_now})
        # The trail follows the high-water mark, upward only.
        if t.get("trail_armed"):
            trail = float(t["high_water"]) * (1 - float(cfg["trail_pct"]))
            if trail > float(t["current_stop"]):
                t["current_stop"] = round(trail, 4)

        # Exit conditions — one signal, one push.
        reason = None
        if px <= float(t["current_stop"]):
            reason = "stop"
        elif px >= float(t["target"]):
            reason = "target"
        elif (t["engine"] == "ignition"
              and int(t.get("sessions_held") or 0) >= int(cfg["ignition_time_stop_sessions"])
              and r_now < 0.5):
            reason = "time"
        elif (t["engine"] in ("pullback", "footprint")
              and int(t.get("sessions_held") or 0) >= int(cfg["pullback_max_hold_sessions"])):
            # Capital that is not working gets recycled. The 5-year replay
            # capped a swing hold at 20 sessions for the same reason.
            reason = "time"
        if reason:
            t["status"] = "exit"
            t["exit_signal"] = {"reason": reason, "price": round(px, 4),
                                "r": round(r_now, 2), "ts": time.time()}
            events.append({"kind": "exit", "reason": reason, "ticket": t,
                           "price": px, "r": r_now})
    return events


def _push_events(events: list[dict]) -> None:
    for e in events:
        t = e["ticket"]
        sym = t["symbol"]
        if e["kind"] == "triggered":
            _notify(f"BUY {sym} {_money(t['notional'])} @ {t['entry']:.2f}",
                    f"Broke {t['trigger_above']:.2f} on the volume it had been "
                    f"building — stop {t['stop']:.2f}, target {t['target']:.2f}, "
                    f"risk {_money(t['risk_usd'])} · expires at the close",
                    sound="buy.wav", data={"type": "ticket", "id": t["id"], "symbol": sym})
        elif e["kind"] == "trail_armed":
            _notify(f"STOP MOVED {sym} {t['current_stop']:.2f}",
                    f"+1R at {e['price']:.2f} — stop to breakeven, trail armed "
                    f"({int(config()['trail_pct'] * 100)}% off the high)",
                    sound="default", data={"type": "ticket", "id": t["id"], "symbol": sym})
        elif e["kind"] == "exit":
            words = {"stop": "stop hit", "target": "target hit",
                     "time": "time stop — it has not paid"}[e["reason"]]
            _notify(f"SELL {sym} now @ {e['price']:.2f}",
                    f"{words} · {e['r']:+.1f}R · {t['shares']:g} sh · confirm the exit in the blotter",
                    sound="sell.wav", data={"type": "ticket", "id": t["id"], "symbol": sym})


# ----------------------------------------------------------------- engines
def from_ignition(movers: list[dict], book: dict | None = None,
                  eq: float | None = None, push_it: bool = True) -> list[dict]:
    """Igniting movers -> armed tickets. Extended names are never ticketed:
    chasing them lost money in every variant measured."""
    with _lock:
        own = book is None
        book = book or load()
        cfg = config(book)
        eq = equity(book) if eq is None else eq
        issued: list[dict] = []
        for m in movers:
            if m.get("stage") != "igniting":
                continue
            price = float(m.get("price") or 0)
            if price <= 0:
                continue
            stop = price * (1 - float(cfg["ignition_stop_pct"]))
            rvol = m.get("rvol")
            why = [
                f"Up {float(m.get('change_pct') or 0):.0f}% today"
                + (f" on {rvol:.0f}x average volume" if rvol else "") + ", still near the high",
                f"${float(m.get('market_cap') or 0) / 1e9:.1f}B cap — small enough to move fast",
                "Lottery size by rule: the stop bounds the loss, the cap bounds the stop failing",
            ]
            t = issue(m["symbol"], "ignition", price, stop, why=why,
                      headline=str(m.get("name") or "")[:40],
                      meta={"change_pct": m.get("change_pct"), "rvol": rvol,
                            "market_cap": m.get("market_cap"), "range_pos": m.get("range_pos")},
                      push_it=push_it, book=book, eq=eq)
            if t:
                issued.append(t)
        if own:
            save(book)
        return issued


def from_pullback(rows: list[dict], book: dict | None = None,
                  eq: float | None = None, push_it: bool = True) -> list[dict]:
    """Pullback setups -> armed tickets. The t=2.48 edge, run concentrated."""
    with _lock:
        own = book is None
        book = book or load()
        eq = equity(book) if eq is None else eq
        issued: list[dict] = []
        for row in rows:
            t = issue(row["symbol"], "pullback", row["entry"], row["stop"],
                      why=row.get("why"),
                      headline=f"RSI {row['rsi_prev']:.0f} to {row['rsi']:.0f}, above the 200-day",
                      meta={"rsi": row.get("rsi"), "rsi_prev": row.get("rsi_prev"),
                            "pct_above_200d": row.get("pct_above_200d"), "atr": row.get("atr")},
                      push_it=push_it, book=book, eq=eq)
            if t:
                issued.append(t)
        if own:
            save(book)
        return issued


def from_footprint(rows: list[dict], book: dict | None = None,
                   eq: float | None = None) -> list[dict]:
    """Accumulation names -> CONDITIONAL watches above the prior day's high.

    Deliberately not orders. Screening at 8x volume concentrates the names
    that touch +50% within a week from 1.3% to 13.7%, but the MEDIAN 5-day
    return at that threshold is -8.1%: both tails fatten and the left one is
    heavier. So the volume buys the name a place on the watchlist and the
    break buys it a position; if the break never comes the ticket expires
    having cost nothing."""
    with _lock:
        own = book is None
        book = book or load()
        cfg = config(book)
        eq = equity(book) if eq is None else eq
        sessions = int(cfg["footprint_watch_sessions"])
        issued: list[dict] = []
        for row in rows:
            trigger = float(row.get("trigger_above") or 0)
            price = float(row.get("price") or 0)
            if trigger <= 0 or price <= 0 or trigger < price * 0.98:
                continue          # a trigger already behind us is not a trigger
            stop = trigger * (1 - float(cfg["footprint_stop_pct"]))
            ratio = row.get("vol_ratio")
            why = [
                f"Trading {ratio:.0f}x its normal volume before any move — the "
                f"earliest honest signal measured" if ratio else
                "Unusual volume before any move",
                f"Waits above {trigger:.2f} (yesterday's high). No break, no trade — "
                f"at this volume the median five-day return is negative",
                f"Stop {stop:.2f}, {int(cfg['footprint_stop_pct'] * 100)}% under the trigger",
            ]
            if row.get("beaten_down"):
                why.insert(1, "Down on the month and suddenly busy — the profile "
                              "the study found before a +50% week")
            t = issue(row["symbol"], "footprint", trigger, stop, why=why,
                      headline=f"{ratio:.0f}x volume, waiting on {trigger:.2f}" if ratio
                      else f"waiting on {trigger:.2f}",
                      meta={"vol_ratio": ratio, "drift_20d": row.get("drift_20d"),
                            "avg_dollar_vol": row.get("avg_dollar_vol")},
                      push_it=False, book=book, eq=eq,
                      trigger_above=trigger,
                      expires_ts=time.time() + sessions * 86400)
            if t:
                issued.append(t)
        if own:
            save(book)
        return issued


# --------------------------------------------------------------- scorecard
def scorecard(book: dict) -> dict:
    """Per-engine record in R. Expectancy and a t-statistic, with n beside
    them — a number without its sample size is how a desk fools itself."""
    by: dict[str, list[float]] = {}
    for t in book["tickets"]:
        if t.get("status") == "closed" and t.get("r_multiple") is not None:
            by.setdefault(t["engine"], []).append(float(t["r_multiple"]))
    out = {}
    for eng, rs in by.items():
        n = len(rs)
        mean = sum(rs) / n
        sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1)) if n > 1 else None
        out[eng] = {
            "n": n, "wins": sum(1 for r in rs if r > 0),
            "win_rate": round(100 * sum(1 for r in rs if r > 0) / n, 1),
            "expectancy_r": round(mean, 3), "total_r": round(sum(rs), 2),
            "t_stat": round(mean / (sd / math.sqrt(n)), 2) if sd else None,
            "best_r": round(max(rs), 2), "worst_r": round(min(rs), 2),
        }
    return out


# ------------------------------------------------------------------- state
def _live_quotes(symbols: list[str]) -> dict:
    from . import market_data
    out: dict = {}
    for sym in dict.fromkeys(symbols):
        try:
            md = market_data.get_price_data(sym)
            if md.history is None or md.history.empty:
                continue
            out[sym] = {"price": float(md.history["Close"].iloc[-1]), "source": md.source}
        except Exception as exc:
            print(f"[sleeve] quote failed for {sym}: {exc!r}")
    return out


def state(with_quotes: bool = True) -> dict:
    """Everything the blotter needs, marked to live prices."""
    book = load()
    cfg = config(book)
    core = _core_book_value()
    cap = capital(cfg, core_value=core)
    open_syms = [t["symbol"] for t in book["tickets"] if t.get("status") in ("live", "exit")]
    quotes = _live_quotes(open_syms) if (with_quotes and open_syms) else {}
    eq = equity(book, quotes, cap=cap)
    rows = []
    for t in sorted(book["tickets"], key=lambda x: -float(x.get("ts") or 0)):
        row = dict(t)
        q = quotes.get(t["symbol"])
        if q and t.get("status") in ("live", "exit"):
            px = float(q["price"])
            row["last_price"] = round(px, 4)
            if t.get("fill_price") and t.get("r_unit"):
                row["r_now"] = round((px - float(t["fill_price"])) / float(t["r_unit"]), 2)
                row["pnl_now"] = round((px - float(t["fill_price"])) * float(t["shares"]), 2)
        rows.append(row)
    live_notional = sum(float(t.get("shares") or 0) * float(t.get("last_price") or t.get("fill_price") or 0)
                        for t in book["tickets"] if t.get("status") in ("live", "exit"))
    curve = book.get("equity_history", [])[-120:]
    bench, bench_note = _benchmark(curve, cap)
    return {
        "config": cfg,
        "capital": cap, "core_value": round(core, 2), "equity": eq,
        "realized": realized_pnl(book), "deployed": round(live_notional, 2),
        "slots_used": _slots_used(book), "issued_today": _issued_today(book),
        "counts": {s: sum(1 for t in book["tickets"] if t.get("status") == s)
                   for s in ("watching", "armed", "live", "exit", "closed",
                             "passed", "expired")},
        "tickets": rows[:60],
        "scorecard": scorecard(book),
        "equity_history": curve,
        "benchmark": bench,
        "benchmark_note": bench_note,
    }


def _benchmark(curve: list[dict], cap: float) -> tuple[list[dict], str]:
    """SPY over the same days, REBASED to the sleeve's starting capital.

    Standing rule in this codebase: never show a return without the index
    beside it. Rebased rather than raw so the two lines share an axis and the
    gap between them IS the out- or under-performance."""
    if len(curve) < 2 or cap <= 0:
        return [], "SPY appears once the sleeve has two days of history."
    try:
        from . import market_data
        md = market_data.get_price_data("SPY")
        if md.source != "live" or md.history is None or md.history.empty:
            return [], "SPY unavailable — the comparison is not being faked."
        closes = {ts.strftime("%Y-%m-%d"): float(c)
                  for ts, c in zip(md.history.index, md.history["Close"])}
    except Exception as exc:
        print(f"[sleeve] benchmark failed: {exc!r}")
        return [], "SPY unavailable — the comparison is not being faked."

    base = None
    out: list[dict] = []
    for row in curve:
        spy = closes.get(row["day"])
        if spy is None:
            continue
        if base is None:
            base = spy
        out.append({"day": row["day"], "equity": round(cap * spy / base, 2)})
    if len(out) < 2:
        return [], "Not enough overlapping SPY days yet."
    first, last = curve[0]["equity"], curve[-1]["equity"]
    you = (last / first - 1) * 100 if first else 0.0
    idx = (out[-1]["equity"] / out[0]["equity"] - 1) * 100
    verb = "ahead of" if you >= idx else "behind"
    return out, (f"SPY {idx:+.1f}% over the same days · sleeve {you:+.1f}% · "
                 f"{verb} the index by {abs(you - idx):.1f} points")


# ---------------------------------------------------------------- heartbeat
def _after_open(now: datetime | None = None) -> bool:
    """Daily-bar engines need the session's first prints; before 09:35 ET the
    last daily bar is still yesterday's and the screen would repeat itself."""
    now = now or _et_now()
    return now.hour * 60 + now.minute >= 9 * 60 + 35


def footprint_rows(cfg: dict, limit: int = 4) -> list[dict]:
    """The loudest accumulation names, with the level each one has to break.

    The trigger is the last COMPLETED session's high — during the day that is
    yesterday's bar, and the check is by date rather than by position so an
    intraday partial bar can never become its own trigger."""
    from . import accumulation, market_data
    rows = [r for r in (accumulation.get().get("results") or []) if r.get("loud")]
    out: list[dict] = []
    for r in rows[:limit * 3]:
        if len(out) >= limit:
            break
        try:
            md = market_data.get_price_data(r["symbol"])
            if md.source != "live" or md.history is None or len(md.history) < 2:
                continue
            hist = md.history
            last_day = hist.index[-1].strftime("%Y-%m-%d")
            bar = hist.iloc[-2] if last_day == _today() else hist.iloc[-1]
            trigger = float(bar["High"])
            price = float(hist["Close"].iloc[-1])
            if trigger <= 0 or price <= 0:
                continue
            out.append({**r, "price": price, "trigger_above": round(trigger, 4)})
        except Exception as exc:
            print(f"[sleeve] footprint level for {r.get('symbol')}: {exc!r}")
    return out


def issue_window(now: datetime | None = None) -> bool:
    """Weekdays 7:00-16:00 ET: pre-market gappers through the closing bell."""
    now = now or _et_now()
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 7 * 60 <= mins < 16 * 60


_LAST_SCAN = {"ts": 0.0}
SCAN_EVERY = 120


def maybe_run(force: bool = False) -> dict | None:
    """Called from the watchdog heartbeat. Issues ignition tickets while the
    market is active, expires stale ones, manages the live ones, marks equity
    once a day. Independent of the core book's owned-only / quiet flags: the
    sleeve is the whole point of watching names you do not own."""
    if not enabled():
        return None
    from .conviction import market_active
    if not force and not market_active():
        return None
    if not force and time.time() - _LAST_SCAN["ts"] < SCAN_EVERY - 5:
        return None
    _LAST_SCAN["ts"] = time.time()

    with _lock:
        book = load()
        cfg = config(book)
        expired = expire(book)

        # New tickets only pre-market through the close. After-hours prints
        # are thin and the relative-volume tell is unmeasured there; a name
        # still igniting at 7:00 tomorrow gets its ticket then, with runway.
        today = _today()
        issued: list[dict] = []
        if force or issue_window():
            # Ignition is intraday and re-scanned every pass; the daily-bar
            # engines run once a session, after the open has printed.
            try:
                from . import runner
                movers = runner.igniting_movers(limit=6)
                issued += from_ignition(movers, book=book, push_it=True)
            except Exception as exc:
                print(f"[sleeve] ignition scan failed: {exc!r}")

            if book.get("daily_scan") != today and (force or _after_open()):
                book["daily_scan"] = today
                try:
                    from . import pullback
                    issued += from_pullback(pullback.scan(cfg=cfg), book=book, push_it=True)
                except Exception as exc:
                    print(f"[sleeve] pullback scan failed: {exc!r}")
                try:
                    issued += from_footprint(footprint_rows(cfg), book=book)
                except Exception as exc:
                    print(f"[sleeve] footprint scan failed: {exc!r}")

        events: list[dict] = []
        watch_syms = [t["symbol"] for t in book["tickets"] if t.get("status") == "watching"]
        open_syms = [t["symbol"] for t in book["tickets"] if t.get("status") == "live"]
        if open_syms or watch_syms:
            quotes = _live_quotes(sorted(set(open_syms + watch_syms)))
            events = check_triggers(book, quotes, cfg) + manage(book, quotes, cfg)
            _push_events(events)

        hist = book.setdefault("equity_history", [])
        if not hist or hist[-1]["day"] != today:
            try:
                hist.append({"day": today, "equity": equity(book, cap=capital(cfg))})
            except Exception:
                pass
        save(book)

    # Colour on the tickets, AFTER they have been issued and pushed. The
    # trader's note is a nice-to-have; a trade never waits on a model call,
    # and a failure here cannot un-issue anything.
    for t in issued:
        try:
            from . import jobs, trader
            jobs.submit(trader.enrich, t["id"])
        except Exception as exc:
            print(f"[sleeve] note for {t['symbol']} not queued: {exc!r}")

    if issued or events or expired:
        print(f"[sleeve] issued={[t['symbol'] for t in issued]} "
              f"events={[(e['kind'], e['ticket']['symbol']) for e in events]} expired={expired}")
    return {"issued": [t["id"] for t in issued],
            "events": [{"kind": e["kind"], "symbol": e["ticket"]["symbol"],
                        "reason": e.get("reason")} for e in events],
            "expired": expired}
