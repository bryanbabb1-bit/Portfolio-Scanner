"""Action journal — a persistent, user-editable record of trades and moves.

Structured entries: date, symbol, action (buy | sell | note), shares, price,
note, source (auto | manual | pin). Auto entries come from diffing the
holdings snapshot on every portfolio read; manual entries let the user record
moves the app didn't see (and edit/delete anything). The journal is shown on
the dashboard and injected into advisor facts so guidance acknowledges
progress and frames the NEXT step, not a restart.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ..config import settings

_JOURNAL_FILE = settings.PORTFOLIO_FILE.parent / "action_journal.json"
_SNAPSHOT_FILE = settings.PORTFOLIO_FILE.parent / "holdings_snapshot.json"
_lock = threading.Lock()

VALID_ACTIONS = {"buy", "sell", "note"}


def _realized(shares, price, cost) -> float | None:
    """Booked $ P/L on a sale: shares x (sale price - cost basis)."""
    if shares and price is not None and cost is not None:
        return round(shares * (price - cost), 2)
    return None

# A single trade cannot be worth more than the book it happens in — you can't
# sell what you don't hold, and cash here is a rounding error. Anything past this
# multiple of the last trusted book value is a corrupt read, not an order.
_MAX_TRADE_VS_BOOK = 2.0

# ...and a position's share count cannot multiply by this much between two reads
# of a 120-second poll. This is the test that survives a baseline which is ALREADY
# poisoned: the value test above measures against the previous book, so if the
# corrupt number is the one sitting in the snapshot it inflates the very yardstick
# it should be failing against, and the recovery read books the giant sell.
# A ratio is immune to that because it doesn't depend on any total.
_MAX_SHARE_RATIO = 20.0

# Legacy free-text action names -> structured actions (one-time migration).
_LEGACY_ACTIONS = {"opened": "buy", "added": "buy", "trimmed": "sell",
                   "sold": "sell", "completed": "note"}


def _migrate(e: dict) -> dict:
    if e.get("action") in VALID_ACTIONS and "note" in e:
        e.setdefault("cost_basis", None)
        e.setdefault("realized_pl", None)
        return e
    return {
        "id": e.get("id") or uuid.uuid4().hex[:12],
        "date": (e.get("date") or "")[:10] or time.strftime("%Y-%m-%d"),
        "symbol": e.get("symbol"),
        "action": _LEGACY_ACTIONS.get(e.get("action"), "note"),
        "shares": e.get("shares"),
        "price": e.get("price"),
        "cost_basis": e.get("cost_basis"),
        "realized_pl": e.get("realized_pl"),
        "note": e.get("note") or e.get("detail") or "",
        "source": e.get("source", "auto"),
        "ts": e.get("ts", time.time()),
    }


def _load() -> list[dict]:
    try:
        with open(_JOURNAL_FILE) as f:
            data = json.load(f)
        return [_migrate(e) for e in data] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    _JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_JOURNAL_FILE, "w") as f:
        json.dump(items[-300:], f, indent=2)


def add_entry(symbol: str | None, action: str, note: str,
              shares: float | None = None, price: float | None = None,
              date: str | None = None, source: str = "auto",
              cost_basis: float | None = None,
              realized_pl: float | None = None) -> dict:
    action = action if action in VALID_ACTIONS else "note"
    # A sell with the pieces but no explicit realized $ → compute it.
    if action == "sell" and realized_pl is None:
        realized_pl = _realized(shares, price, cost_basis)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "date": (date or time.strftime("%Y-%m-%d"))[:10],
        "symbol": (symbol or "").upper().strip() or None,
        "action": action,
        "shares": shares,
        "price": price,
        "cost_basis": cost_basis,
        "realized_pl": realized_pl,
        "note": (note or "").strip(),
        "source": source,  # auto | manual | pin
        "ts": time.time(),
    }
    with _lock:
        items = _load()
        # Dedup: an identical note for the same symbol from an automated source
        # is a duplicate, not a second event — never spam the ledger. Sells are
        # exempt: each sale is a distinct financial event to bank.
        if source in ("pin", "auto") and entry["note"] and action != "sell":
            for e in items:
                if (e.get("symbol") == entry["symbol"]
                        and e.get("note") == entry["note"]
                        and e.get("source") == source):
                    return e
        items.append(entry)
        _save(items)
    return entry


def update_entry(entry_id: str, fields: dict) -> dict | None:
    allowed = {"date", "symbol", "action", "shares", "price", "note",
               "cost_basis", "realized_pl"}
    with _lock:
        items = _load()
        for e in items:
            if e["id"] == entry_id:
                for k, v in fields.items():
                    if k not in allowed or v is None:
                        continue
                    if k == "symbol":
                        v = (str(v).upper().strip() or None)
                    if k == "action" and v not in VALID_ACTIONS:
                        continue
                    if k == "date":
                        v = str(v)[:10]
                    e[k] = v
                # Editing the sale price / shares / cost re-books the realized
                # gain — unless the user typed a realized figure directly.
                if e.get("action") == "sell" and "realized_pl" not in fields:
                    rp = _realized(e.get("shares"), e.get("price"), e.get("cost_basis"))
                    if rp is not None:
                        e["realized_pl"] = rp
                _save(items)
                return e
    return None


def realized_total() -> float:
    """All-time booked P/L across every sell entry (auto + manual)."""
    return round(sum(float(e.get("realized_pl") or 0)
                     for e in _load() if e.get("action") == "sell"), 2)


def delete_entry(entry_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [e for e in items if e["id"] != entry_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def clear() -> int:
    """Wipe the whole ledger — 'start fresh' when deploying a new strategy so
    the advisor looks forward, not back. Re-baselines the holdings snapshot to
    current so no phantom trades are auto-detected on the next read."""
    with _lock:
        n = len(_load())
        _save([])
        try:
            from . import portfolio as pf_service
            holdings = pf_service.load_portfolio().get("holdings", [])
            snap = {h["symbol"].upper(): {"shares": float(h.get("shares", 0) or 0),
                                          "cost": float(h.get("cost_basis", 0) or 0)}
                    for h in holdings}
            with open(_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(snap, f, indent=2)
        except Exception:
            pass
    return n


def list_entries(days: int = 30) -> list[dict]:
    cutoff = time.strftime("%Y-%m-%d",
                           time.localtime(time.time() - days * 86400))
    items = [e for e in _load() if e.get("date", "") >= cutoff]
    return sorted(items, key=lambda e: (e.get("date", ""), e.get("ts", 0)),
                  reverse=True)


def _norm_snap(raw) -> dict:
    """Read a snapshot in either the legacy {sym: shares} or the current
    {sym: {shares, cost}} format."""
    out: dict[str, dict] = {}
    if isinstance(raw, dict):
        for sym, v in raw.items():
            if isinstance(v, dict):
                out[sym] = {"shares": float(v.get("shares", 0) or 0),
                            "cost": v.get("cost")}
            else:
                out[sym] = {"shares": float(v or 0), "cost": None}
    return out


def _sale_price(sym: str) -> float | None:
    """Best proxy for the price a position was sold at: the current market
    price (the user just deleted it, so 'now' is the fill). Editable later.

    Refuses a MOCK price. In auto mode a failed live fetch degrades to mock, so
    booking realized P/L against it invents a gain or loss out of nothing —
    AVGO was recorded sold at $175 while it traded at $382. No price means the
    entry is journalled without realized P/L rather than with a fictional one.
    """
    try:
        from . import market_data
        from ..config import settings as _s
        md = market_data.get_price_data(sym)
        if md.source == "mock" and _s.DATA_MODE != "mock":
            print(f"[journal] refusing mock sale price for {sym}")
            return None
        return round(float(md.history["Close"].iloc[-1]), 2)
    except Exception:
        return None


def retire_closed_symbol(sym: str) -> None:
    """Stand down the instructions attached to a position that just closed.

    The order is filled; anything still telling the client to place it is stale.
    Failures are swallowed on purpose — tidying up must never be able to stop a
    real fill from being journaled.
    """
    try:
        from . import pins as pins_service
        retired = pins_service.retire_for_symbol(sym)
        if retired:
            print(f"[journal] {sym} closed — retired {len(retired)} stale pin(s)")
    except Exception as exc:
        print(f"[journal] could not retire pins for {sym}: {exc!r}")
    try:
        from . import stance as stance_service
        if stance_service.drop(sym):
            print(f"[journal] {sym} closed — dropped its standing call")
    except Exception as exc:
        print(f"[journal] could not drop stance for {sym}: {exc!r}")


def snapshot_and_diff(holdings: list[dict]) -> list[dict]:
    """Compare current holdings to the last snapshot; journal any trades and
    BOOK realized P/L on trims/closes (shares sold x (sale price - cost basis)).

    First run just records the baseline silently. Share deltas under 0.5%
    are ignored (float noise / DRIP dust).
    """
    current = {
        h["symbol"].upper(): {"shares": float(h.get("shares", 0) or 0),
                              "cost": float(h.get("cost_basis", 0) or 0)}
        for h in holdings if h.get("symbol")
    }
    with _lock:
        try:
            with open(_SNAPSHOT_FILE) as f:
                prev = _norm_snap(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            prev = {}

        # SANITY GATE, before the snapshot is overwritten.
        #
        # A caller handing us a short or empty holdings list is far more likely
        # to be a bad read than a client who liquidated their whole book
        # between two page loads. Without this guard the diff booked a "closed
        # the position" sell for every real holding — at a MOCK price, since
        # the fallback fires on the same failures — and then re-opened them all
        # on the next good read. Repeated, that produced tens of thousands of
        # dollars of phantom realized losses and a -217% reported return.
        suspect = ""
        if prev and not current:
            suspect = "holdings list was empty"
        elif prev and len(current) * 2 < len(prev):
            suspect = (f"holdings dropped from {len(prev)} to {len(current)} "
                       f"in one read")

        # Second gate: a SINGLE position's share count moving by an absurd amount
        # in one read is also a bad read — a decimal point that went missing, not
        # a trade. The count gate above cannot see this, because the number of
        # holdings never changes.
        #
        # On 2026-07-29 NVDA's shares came back as 898497 instead of 8.98497. The
        # diff booked an 898,489-share buy, then an 898,488-share sell on the way
        # back down, for -$11,779,177.88 of phantom realized loss and a reported
        # total return of -117,299%.
        #
        # The test is value-based and measured against the PREVIOUS book, which is
        # the copy we still trust: you cannot sell more than you hold or buy with
        # money you do not have, so a single trade worth several times the whole
        # book is impossible by construction.
        if not suspect and prev:
            prev_book = sum((p.get("shares") or 0) * (p.get("cost") or 0)
                            for p in prev.values())
            for sym, cur in current.items():
                old = prev.get(sym)
                if not old or not old.get("shares"):
                    continue
                old_sh, new_sh = old["shares"], cur["shares"]
                delta = abs(new_sh - old_sh)
                basis = old.get("cost") or cur.get("cost") or 0
                if not delta:
                    continue
                ratio = (max(old_sh, new_sh) / min(old_sh, new_sh)
                         if min(old_sh, new_sh) > 0 else 0)
                if ratio > _MAX_SHARE_RATIO:
                    suspect = (f"{sym} shares moved {old_sh:g} -> {new_sh:g}, "
                               f"a {ratio:,.0f}x change in one read")
                    break
                if basis and prev_book and delta * basis > _MAX_TRADE_VS_BOOK * prev_book:
                    suspect = (
                        f"{sym} shares moved {old_sh:g} -> {new_sh:g}, "
                        f"implying a ${delta * basis:,.0f} trade against a "
                        f"${prev_book:,.0f} book")
                    break

        if suspect:
            print(f"[journal] ignoring suspicious snapshot ({suspect}); "
                  f"keeping the previous baseline")
            return []          # and deliberately do NOT overwrite the snapshot

        _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
    if not prev:
        return []

    entries: list[dict] = []

    def _sell(sym, sold, cost, note):
        sale = _sale_price(sym)
        entries.append(add_entry(sym, "sell", note, shares=sold, price=sale,
                                 cost_basis=cost, realized_pl=_realized(sold, sale, cost),
                                 source="auto"))

    for sym, cur in current.items():
        old = prev.get(sym, {"shares": 0, "cost": None})
        old_sh, new_sh = old["shares"], cur["shares"]
        if old_sh == 0 and new_sh > 0:
            entries.append(add_entry(sym, "buy", "Opened a new position",
                                     shares=new_sh, cost_basis=cur["cost"], source="auto"))
        elif new_sh > old_sh > 0 and (new_sh - old_sh) / old_sh > 0.005:
            entries.append(add_entry(sym, "buy", f"Added shares ({old_sh:g} -> {new_sh:g})",
                                     shares=round(new_sh - old_sh, 4),
                                     cost_basis=cur["cost"], source="auto"))
        elif new_sh < old_sh and old_sh > 0 and (old_sh - new_sh) / old_sh > 0.005:
            cost = old["cost"] if old["cost"] is not None else cur["cost"]
            _sell(sym, round(old_sh - new_sh, 4), cost,
                  f"Trimmed ({old_sh:g} -> {new_sh:g})")

    for sym, old in prev.items():
        if old["shares"] > 0 and current.get(sym, {"shares": 0})["shares"] == 0:
            # The order is filled and the position is gone, so anything still
            # telling the client to place it has to stand down. Otherwise the
            # brief keeps reading an open "Sell all $152 GEV" pin and a standing
            # SELL stance off a position that closed days ago, and repeats the
            # instruction every morning — which is exactly what GEV did.
            retire_closed_symbol(sym)
            _sell(sym, round(old["shares"], 4), old["cost"],
                  f"Closed the position ({old['shares']:g} sh)")

    return entries


def facts_block(days: int = 30, limit: int = 20) -> str:
    """Journal formatted for advisor prompts; empty string when no history."""
    entries = list_entries(days)[:limit]
    if not entries:
        return ""
    lines = [f"Actions the client has ALREADY TAKEN (last {days} days, newest first):"]
    for e in entries:
        sym = e["symbol"] or "PORTFOLIO"
        qty = f" {e['shares']:g} shares" if e.get("shares") else ""
        px = f" @ ${e['price']:g}" if e.get("price") else ""
        rl = (f" (realized {e['realized_pl']:+,.0f})"
              if e.get("realized_pl") not in (None, 0) else "")
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"  {e['date']}: {e['action'].upper()} {sym}{qty}{px}{rl}{note}")
    return "\n".join(lines)
