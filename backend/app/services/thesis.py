"""A thesis-driven paper book. One view, stated falsifiably, held aggressively.

This is not the mechanical harness. There is no backtest to hide behind: the
thesis below is a claim about the world that will be right or wrong, and the
book exists so it can be scored rather than rationalised afterwards.

RULES OF ENGAGEMENT
-------------------
  * $1,000 to start, no leverage, no crypto, sim only.
  * Buy or sell whenever. Concentration is allowed and expected.
  * Zero is a loss. The account can go to zero and that is a real outcome.

THE HONEST ODDS
---------------
The target is 100x. A book of common stock cannot do that — for the holdings to
100x the companies must 100x, and a $2B name becoming $200B inside a few years
is not a plan, it is a lottery ticket. Reaching $100k requires convexity (long
options) and repeatedly re-risking winners, and even executed perfectly the
probability is low single digits. That is recorded here so nobody has to
reconstruct the expectation later.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field

from ..config import settings

_BOOK_FILE = settings.PORTFOLIO_FILE.parent / "thesis_book.json"

START_CASH = 1000.0
GOAL = 100_000.0


# ---------------------------------------------------------------- the thesis
THESIS = {
    "name": "Power before 2028",
    "one_liner": (
        "The AI buildout's binding constraint is electricity DELIVERED before "
        "2028, and the market is mispricing when relief arrives — not whether."
    ),
    "argument": [
        "The US interconnection queue is over 2,600 GW with ~5-year waits and "
        "~80% withdrawal rates. Roughly half of the AI data centres planned for "
        "2026 are delayed, leaving a ~7 GW gap that bottlenecks about $650B of "
        "hyperscaler capex.",
        "This is a PHYSICAL constraint, not a capital one. Money cannot buy an "
        "interconnection any faster, which is why hyperscalers are signing "
        "direct nuclear PPAs and restarting shuttered plants.",
        "SMR pure-plays are being priced as the answer to this gap. They are "
        "not: the earliest commercial units target late 2027 / early 2028 by "
        "their own guidance, and nuclear timelines slip. They cannot address a "
        "2026-27 shortage.",
        "So the market is confusing 'right about the problem' with 'able to "
        "solve it on the binding timeline'. The mispricing is in WHEN.",
        "NuScale is the asymmetry inside that confusion: the only NRC-certified "
        "SMR design, trading under $10 after an earnings miss, while capital "
        "chases pre-revenue names with no approval. If the gap forces a "
        "panic bid for anything permitted, certification is the scarce asset.",
    ],
    # Written BEFORE the positions, so they cannot be quietly revised later.
    "falsifiers": [
        "A pure-play SMR signs a binding, funded PPA delivering power before "
        "2028 — the 'they cannot help on the binding timeline' leg is then wrong.",
        "Interconnection reform or a grid-queue fast-track materially clears the "
        "backlog — the bottleneck premise dissolves.",
        "Hyperscaler capex guidance is cut hard: the demand side breaks and the "
        "whole bottleneck stops mattering.",
        "Turbine and grid-equipment backlogs shrink — the 'deliverable now' leg "
        "was not actually scarce.",
        "NuScale loses or materially delays its certification advantage.",
    ],
    "kill_switch": (
        "If the book is down 50% with no falsifier having triggered, the thesis "
        "is right and the EXPRESSION is wrong: close everything and re-express "
        "rather than average down."
    ),
    "honest_odds": (
        "Common stock cannot 100x. This book plays for 3-10x and is the funding "
        "stage; the 100x tail needs long-dated calls layered on once the thesis "
        "shows evidence of working. P(reaching $100k) is low single digits."
    ),
}


@dataclass
class Position:
    symbol: str
    shares: float
    entry: float
    opened: str
    conviction: str          # core | satellite | anchor
    why: str
    closed: str | None = None
    exit_price: float | None = None
    realized: float = 0.0


@dataclass
class Book:
    cash: float = START_CASH
    positions: list = field(default_factory=list)
    log: list = field(default_factory=list)

    @property
    def open_positions(self) -> list:
        return [p for p in self.positions if not p.get("closed")]


def load() -> dict:
    try:
        with open(_BOOK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"cash": START_CASH, "positions": [], "log": [],
                "started": time.strftime("%Y-%m-%d")}


def save(book: dict) -> None:
    _BOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_BOOK_FILE, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=2)


# ------------------------------------------------------------ my risk rules
RULES = {
    "capital": "$1,000. Equities only. No crypto, no leverage, no options.",
    "positions": "4-6 names. 15-30% each. Concentrated on purpose.",
    "stop_loss": "-20% hard stop per position, from the fill. No exceptions, "
                 "no averaging down into one.",
    "book_stop": "-35% on the whole book: stop opening, close everything, "
                 "reassess. That is the most I am willing to lose.",
    "take_profit": "Trim 1/3 at +50%. The rest rides a 25% trailing stop from "
                   "its high, so a winner can actually become a big winner.",
    "cash": "Cash is a position. If nothing qualifies, hold it.",
    "review": "Marked every session. Stops checked on the close.",
}

STOP_PCT = 0.20
TRAIL_PCT = 0.25
TRIM_AT = 0.50
BOOK_STOP_PCT = 0.35


def queue(book: dict, symbol: str, dollars: float, conviction: str, why: str) -> dict:
    """Stage an order to fill at the NEXT market open.

    Orders are staged rather than filled instantly because a simulation that
    fills at a price already on the screen is just backdating. These execute at
    tomorrow's open, at whatever that open turns out to be.
    """
    book.setdefault("pending", []).append({
        "symbol": symbol.upper(), "dollars": round(dollars, 2),
        "conviction": conviction, "why": why,
        "queued": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return book


def execute_pending(book: dict, opens: dict) -> list[str]:
    """Fill every staged order at the supplied opening prices."""
    filled: list[str] = []
    for order in list(book.get("pending", [])):
        px = opens.get(order["symbol"])
        if not px:
            continue
        buy(book, order["symbol"], order["dollars"], float(px),
            order["conviction"], order["why"])
        pos = book["positions"][-1]
        pos["stop"] = round(float(px) * (1 - STOP_PCT), 4)
        pos["high_water"] = round(float(px), 4)
        book["pending"].remove(order)
        filled.append(f"{order['symbol']} @ {float(px):.2f}")
    return filled


def check_stops(book: dict, quotes: dict) -> list[str]:
    """Trail the winners, cut the losers. Returns what it did and why."""
    acted: list[str] = []
    for p in book["positions"]:
        if p.get("closed"):
            continue
        q = quotes.get(p["symbol"])
        if not q or not q.get("price"):
            continue
        px = float(q["price"])
        # Ratchet the high-water mark, then trail from it — never downward.
        p["high_water"] = round(max(p.get("high_water", p["entry"]), px), 4)
        gain = px / p["entry"] - 1
        if gain >= TRIM_AT and not p.get("trimmed"):
            p["trimmed"] = True
            trail = round(p["high_water"] * (1 - TRAIL_PCT), 4)
            p["stop"] = round(max(p.get("stop", 0), trail), 4)
            acted.append(f"{p['symbol']} +{gain * 100:.0f}%: trailing stop armed "
                         f"at {p['stop']:.2f}")
        elif p.get("trimmed"):
            trail = round(p["high_water"] * (1 - TRAIL_PCT), 4)
            if trail > p.get("stop", 0):
                p["stop"] = trail
        if px <= p.get("stop", 0):
            sell(book, p["symbol"], px,
                 f"stop hit at {px:.2f} (stop {p['stop']:.2f})")
            acted.append(f"{p['symbol']} STOPPED OUT at {px:.2f}")
    return acted


def buy(book: dict, symbol: str, dollars: float, price: float,
        conviction: str, why: str) -> dict:
    """Open or add to a position. Refuses to spend cash the book doesn't have —
    no leverage means no leverage, even in a simulation."""
    sym = symbol.upper()
    dollars = min(dollars, book["cash"])
    if dollars <= 0 or price <= 0:
        raise ValueError("no cash available or bad price")
    shares = round(dollars / price, 6)
    book["cash"] = round(book["cash"] - shares * price, 2)
    book["positions"].append(asdict(Position(
        symbol=sym, shares=shares, entry=round(price, 4),
        opened=time.strftime("%Y-%m-%d"), conviction=conviction, why=why)))
    book["log"].append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "action": "buy", "symbol": sym,
                        "shares": shares, "price": round(price, 4), "why": why})
    return book


def sell(book: dict, symbol: str, price: float, why: str) -> dict:
    sym = symbol.upper()
    for p in book["positions"]:
        if p["symbol"] == sym and not p.get("closed"):
            proceeds = p["shares"] * price
            p["closed"] = time.strftime("%Y-%m-%d")
            p["exit_price"] = round(price, 4)
            p["realized"] = round(proceeds - p["shares"] * p["entry"], 2)
            book["cash"] = round(book["cash"] + proceeds, 2)
            book["log"].append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "action": "sell", "symbol": sym,
                                "shares": p["shares"], "price": round(price, 4),
                                "why": why})
    return book


def _et_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))


def _live_quotes(symbols: list[str]) -> tuple[dict, dict]:
    """(last prices, session opens) — LIVE data only.

    Anything mock-sourced is dropped rather than traded on. This codebase has
    already booked fake realized losses off mock prices once; a book that fills
    orders against generated data would be worse than no book.
    """
    from . import market_data
    last: dict = {}
    opens: dict = {}
    for sym in dict.fromkeys(symbols):
        try:
            md = market_data.get_price_data(sym)
            if md.source != "live" or md.history is None or md.history.empty:
                print(f"[thesis] {sym}: {md.source} data — skipped")
                continue
            last[sym] = {"price": float(md.history["Close"].iloc[-1])}
            opens[sym] = float(md.history["Open"].iloc[-1])
        except Exception as exc:
            print(f"[thesis] {sym}: quote failed ({exc!r})")
    return last, opens


def maybe_run(force: bool = False) -> dict | None:
    """Run the book. Called from the watchdog heartbeat, so it manages itself.

    Fills staged orders at the session open, trails and cuts per the rules,
    records one equity mark a day, and pushes only when something actually
    happened. Silent otherwise — a daily "nothing changed" notification is how
    notifications get muted.
    """
    et = _et_now()
    today = et.strftime("%Y-%m-%d")
    if not force:
        if et.weekday() >= 5:
            return None
        mins = et.hour * 60 + et.minute
        # After the open has printed, before the close is stale.
        if mins < 9 * 60 + 35 or mins > 16 * 60 + 30:
            return None

    book = load()
    already = book.get("last_run") == today
    if already and not book.get("pending") and not force:
        return None

    symbols = [o["symbol"] for o in book.get("pending", [])]
    symbols += [p["symbol"] for p in book["positions"] if not p.get("closed")]
    if not symbols:
        return None
    quotes, opens = _live_quotes(symbols)
    if not quotes:
        return None                     # no live data: do nothing at all

    filled = execute_pending(book, opens)
    acted = check_stops(book, quotes)

    scored = mark(book, quotes)
    hist = book.setdefault("equity_history", [])
    if not hist or hist[-1]["day"] != today:
        hist.append({"day": today, "equity": scored["equity"]})
    book["last_run"] = today
    save(book)

    if filled or acted:
        try:
            from . import push
            lines = filled + acted
            push.send("THESIS BOOK",
                      f"${scored['equity']:,.0f} ({scored['return_pct']:+.1f}%) · "
                      + "; ".join(lines[:3]),
                      data={"type": "thesis"})
        except Exception as exc:
            print(f"[thesis] push failed: {exc!r}")

    return {"filled": filled, "stop_actions": acted,
            "equity": scored["equity"], "return_pct": scored["return_pct"]}


def mark(book: dict, quotes: dict) -> dict:
    """Mark the book to live prices. Returns the scorecard."""
    rows = []
    equity = book["cash"]
    for p in book["positions"]:
        if p.get("closed"):
            continue
        q = quotes.get(p["symbol"])
        price = float(q["price"]) if q and q.get("price") else p["entry"]
        value = p["shares"] * price
        equity += value
        rows.append({
            **p, "price": round(price, 4), "value": round(value, 2),
            "pl": round(value - p["shares"] * p["entry"], 2),
            "pl_pct": round((price / p["entry"] - 1) * 100, 2),
        })
    realized = sum(p.get("realized", 0) for p in book["positions"] if p.get("closed"))
    return {
        "thesis": THESIS,
        "started": book.get("started"),
        "cash": round(book["cash"], 2),
        "equity": round(equity, 2),
        "realized": round(realized, 2),
        "return_pct": round((equity / START_CASH - 1) * 100, 2),
        "goal": GOAL,
        "progress_pct": round(equity / GOAL * 100, 3),
        "multiple_needed": round(GOAL / equity, 1) if equity > 0 else None,
        "positions": sorted(rows, key=lambda r: -r["value"]),
        "closed": [p for p in book["positions"] if p.get("closed")],
        "log": book["log"][-40:],
    }
