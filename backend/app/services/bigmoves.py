"""Eyes and ears on the whole market — the ones you would want to be woken for.

THE BRIEF
---------
"The goal is to get notified when big shit happens so we can be a part of a big
rally. Ignore the current cash available. I need to know."

So this ignores the book, ignores the cash, and ignores whether the desk would
approve of the trade. It watches all of it and says something when something
real happens. Whether to act is Bryan's call; not knowing was never a choice he
made, it was a side effect of settings nobody revisited.

WHY THE THRESHOLD IS WHERE IT IS
--------------------------------
Measured against 43 sessions of the whole US market (backend/studies):

    >= +15% on a $50M/day name    6.3 a session   unusable as a notification
    >= +30%                       0.67 a session  busiest day: 4
    >= +40%                       0.35 a session  busiest day: 2
    >= +50%                       0.23 a session

+40% on a name that already traded $50M a day is 15 events in 43 sessions — one
push every three days, never more than two in a day, and MRNA's +177% sits at
the top of that list. That is a notification you will still read in a month.

The dollar-volume floor is doing as much work as the move: it is what separates
a real company being repriced from a shell being pumped. MRNA traded $426M a
day before it doubled.

WHY EVERYTHING ELSE IS NOT A PUSH
---------------------------------
On 2026-07-30 sixty names moved 15%+ on a sector-wide AI melt-up. Sixty pushes
is not eyes and ears, it is a reason to turn off notifications — and a channel
that has been muted cannot deliver the one that matters. So the wider tier is
collected, shown in the app, and summarised in ONE digest after the close.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "bigmoves.json"
TTL = 120                      # the heartbeat's own cadence

# ---- the loud tier: worth interrupting you for -----------------------------
ALERT_MOVE = 40.0              # per cent on the session
ALERT_DOLLAR_VOL = 50_000_000  # traded this much a day BEFORE the move

# ---- the wide tier: worth seeing, not worth buzzing ------------------------
BIG_MOVE = 15.0                # on a name that already trades real money
BIG_DOLLAR_VOL = 50_000_000
RUNNER_MOVE = 25.0             # or a smaller name really ripping
RUNNER_DOLLAR_VOL = 1_000_000
RUNNER_PRICE = 3.00

# Above this many wide-tier movers, the day is the story, not any one name.
CLUSTER = 12
DIGEST_HOUR_ET = 16            # one summary after the close, never during


def _read() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _write(d: dict) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[bigmoves] persist failed: {exc!r}")


def _et() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _prior_dollar_volume(row: dict) -> float:
    """What this name traded, in dollars, on a normal day before today.

    Deliberately uses the AVERAGE volume and the pre-move price. Today's volume
    is enormous by definition — judging a mover by the liquidity its own spike
    created would let any pumped shell through.
    """
    avg = row.get("avg_vol")
    price = row.get("price") or 0
    chg = row.get("change_pct") or 0
    prev = price / (1 + chg / 100) if chg > -100 else price
    return float(avg or 0) * float(prev or 0)


def classify(row: dict) -> str | None:
    """'alert', 'big', 'runner', or None if it does not clear any bar."""
    chg = float(row.get("change_pct") or 0)
    price = float(row.get("price") or 0)
    dv = _prior_dollar_volume(row)
    if chg >= ALERT_MOVE and dv >= ALERT_DOLLAR_VOL:
        return "alert"
    if chg >= BIG_MOVE and dv >= BIG_DOLLAR_VOL:
        return "big"
    if chg >= RUNNER_MOVE and dv >= RUNNER_DOLLAR_VOL and price >= RUNNER_PRICE:
        return "runner"
    return None


def _scan_market() -> list[dict]:
    """Everything moving hard right now, with NO market-cap ceiling.

    The ceiling is the specific reason the existing Runner Radar could not see
    MRNA: that engine caps at $12B because it hunts low-float microcaps, and
    Moderna was a $67B company. A screen for "something enormous just happened"
    cannot have an upper bound on size.
    """
    if settings.DATA_MODE == "mock":
        return []
    rows: dict[str, dict] = {}
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q

        wide = Q("and", [
            Q("gt", ["percentchange", 12]),
            Q("gt", ["dayvolume", 200_000]),
        ])
        for src in (wide, "day_gainers", "most_actives"):
            try:
                kw = {"count": 100}
                if not isinstance(src, str):
                    kw.update(sortField="percentchange", sortAsc=False)
                res = yf.screen(src, **kw)
                quotes = res.get("quotes", []) if isinstance(res, dict) else []
            except Exception as exc:
                print(f"[bigmoves] screener {src!r}: {exc!r}")
                continue
            for q in quotes:
                sym = (q.get("symbol") or "").upper()
                if not sym or not sym.isalpha():
                    continue          # drop warrants, units, foreign lines
                state = q.get("marketState", "REGULAR")
                if state in ("PRE", "PREPRE") and q.get("preMarketChangePercent") is not None:
                    chg, price = q.get("preMarketChangePercent"), q.get("preMarketPrice")
                elif state in ("POST", "POSTPOST") and q.get("postMarketChangePercent") is not None:
                    chg, price = q.get("postMarketChangePercent"), q.get("postMarketPrice")
                else:
                    chg, price = q.get("regularMarketChangePercent"), q.get("regularMarketPrice")
                if chg is None or price is None:
                    continue
                rows.setdefault(sym, {
                    "symbol": sym,
                    "name": q.get("shortName") or q.get("longName") or sym,
                    "change_pct": round(float(chg), 1),
                    "price": float(price),
                    "market_cap": q.get("marketCap"),
                    "volume": q.get("regularMarketVolume"),
                    "avg_vol": (q.get("averageDailyVolume3Month")
                                or q.get("averageDailyVolume10Day")),
                })
    except Exception as exc:
        print(f"[bigmoves] scan unavailable: {exc!r}")
    return list(rows.values())


def _why(symbol: str) -> str:
    """The headline behind the move — the difference between a Phase 3 and a pump."""
    try:
        import yfinance as yf
        for n in (yf.Ticker(symbol).news or [])[:1]:
            c = n.get("content", n)
            return str(c.get("title") or "")[:160]
    except Exception:
        pass
    return ""


def scan(force: bool = False) -> dict:
    """Look, record, and push the ones that clear the loud bar."""
    state = _read()
    if not force and time.time() - float(state.get("ts", 0)) < TTL:
        return {**state, "cached": True}

    et = _et()
    today = et.strftime("%Y-%m-%d")
    if state.get("date") != today:          # a new session forgets yesterday
        state = {"date": today, "pushed": [], "digest_sent": None}

    found = []
    for row in _scan_market():
        tier = classify(row)
        if not tier:
            continue
        found.append({**row, "tier": tier,
                      "prior_dollar_vol": round(_prior_dollar_volume(row))})
    found.sort(key=lambda r: -r["change_pct"])

    alerts = [r for r in found if r["tier"] == "alert"]
    pushed = set(state.get("pushed") or [])
    fresh = [r for r in alerts if r["symbol"] not in pushed]

    for r in fresh:
        r["why"] = _why(r["symbol"])
        try:
            from . import push
            push.send(
                f"{r['symbol']} +{r['change_pct']:.0f}% — {r['name'][:40]}",
                (r["why"] or "No headline yet — check the tape.")
                + f"  (${r['prior_dollar_vol']/1e6:,.0f}M/day name)",
                data={"type": "bigmove", "symbol": r["symbol"]},
            )
            pushed.add(r["symbol"])
        except Exception as exc:
            print(f"[bigmoves] push failed for {r['symbol']}: {exc!r}")

    # One digest after the close, naming names — never a bare count.
    wide = [r for r in found if r["tier"] != "alert"]
    if (et.hour >= DIGEST_HOUR_ET and state.get("digest_sent") != today
            and (wide or alerts)):
        try:
            from . import push
            top = ", ".join(f"{r['symbol']} +{r['change_pct']:.0f}%"
                            for r in found[:3])
            body = (f"Broad move — {len(found)} names ran today. Biggest: {top}"
                    if len(wide) >= CLUSTER
                    else f"{len(found)} names ran today: {top}")
            push.send("MOVERS TODAY", body, data={"type": "bigmove_digest"})
            state["digest_sent"] = today
        except Exception as exc:
            print(f"[bigmoves] digest failed: {exc!r}")

    state.update(ts=time.time(), pushed=sorted(pushed), movers=found,
                 cluster=len(wide) >= CLUSTER)
    _write(state)
    return {**state, "cached": False}


def latest() -> dict:
    """What the last scan saw, for the dashboard. Never triggers a scan."""
    s = _read()
    return {"ts": s.get("ts"), "date": s.get("date"),
            "movers": s.get("movers") or [], "cluster": bool(s.get("cluster")),
            "thresholds": {"alert_move": ALERT_MOVE,
                           "alert_dollar_vol": ALERT_DOLLAR_VOL,
                           "big_move": BIG_MOVE, "runner_move": RUNNER_MOVE}}
