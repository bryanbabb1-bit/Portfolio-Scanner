"""Signal scorecard — advice is only good if it's right, so measure it.

Every conviction signal and watchpoint hit is recorded with its fire price.
The scorecard replays them against current prices: per-rule win rate and
average forward return (sign-adjusted — a SELL signal 'wins' when the price
falls). Over time this shows which rules earn their thresholds and which
need retuning.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "signal_history.json"


def purge(symbol: str) -> int:
    """Drop every recorded signal for a symbol. Returns how many went.

    For tickers that were never real (a typo, a delisting): their rows can
    never be graded, so they are noise in the ledger forever."""
    sym = (symbol or "").upper()
    with _lock:
        items = _load()
        keep = [x for x in items if x.get("symbol", "").upper() != sym]
        removed = len(items) - len(keep)
        if removed:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_FILE, "w", encoding="utf-8") as f:
                json.dump(keep, f, indent=2)
        return removed
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        with open(_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def record(sig: dict) -> None:
    """Idempotently append a fired signal's entry price for later grading."""
    if not sig.get("id") or not sig.get("price"):
        return
    with _lock:
        items = _load()
        if any(x["id"] == sig["id"] for x in items):
            return
        items.append({
            "id": sig["id"],
            "symbol": sig["symbol"],
            "side": sig.get("side", "buy"),
            "rule": sig.get("rule", "unknown"),
            "price": float(sig["price"]),
            "ts": float(sig.get("ts", time.time())),
            "date": time.strftime("%Y-%m-%d", time.localtime(
                float(sig.get("ts", time.time())))),
        })
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w") as f:
            json.dump(items[-500:], f, indent=2)


def compute(price_of=None) -> dict:
    """Grade every recorded signal against current prices.

    price_of(symbol) -> float | None; defaults to cached market data."""
    if price_of is None:
        from . import market_data

        def price_of(sym: str):
            try:
                md = market_data.get_price_data(sym)
            except Exception:
                return None
            # A live fetch that FAILED degrades to mock in auto mode. Grading
            # a real fired signal against an invented price manufactures a
            # win/loss out of nothing — exactly how a stale typo'd ticker
            # (APPL) polluted the live record with a fabricated result. Only
            # refuse when mock is a fallback; when DATA_MODE is genuinely
            # "mock" (tests, demos) it is the expected source.
            if md.source == "mock" and settings.DATA_MODE != "mock":
                return None
            try:
                return float(md.history["Close"].iloc[-1])
            except (IndexError, KeyError, TypeError, ValueError):
                return None

    now = time.time()
    graded: list[dict] = []
    ungraded: list[str] = []
    for e in _load():
        cur = price_of(e["symbol"])
        if cur is None or not e["price"]:
            if e["symbol"] not in ungraded:
                ungraded.append(e["symbol"])
            continue
        fwd = (cur / e["price"] - 1) * 100
        effective = fwd if e["side"] == "buy" else -fwd
        graded.append({**e, "current": round(cur, 2),
                       "fwd_return_pct": round(fwd, 2),
                       "effective_pct": round(effective, 2),
                       "age_days": round((now - e["ts"]) / 86400, 1)})

    rules: dict[str, list[dict]] = {}
    for g in graded:
        rules.setdefault(g["rule"], []).append(g)

    rule_stats = []
    for rule, sigs in rules.items():
        effs = [s["effective_pct"] for s in sigs]
        rule_stats.append({
            "rule": rule,
            "signals": len(sigs),
            "win_rate": round(100 * sum(1 for e in effs if e > 0) / len(effs), 0),
            "avg_effective_pct": round(sum(effs) / len(effs), 2),
            "best_pct": round(max(effs), 2),
            "worst_pct": round(min(effs), 2),
        })
    rule_stats.sort(key=lambda r: -r["avg_effective_pct"])

    overall = [g["effective_pct"] for g in graded]
    return {
        "count": len(graded),
        "overall_win_rate": round(100 * sum(1 for e in overall if e > 0)
                                  / len(overall), 0) if overall else None,
        "overall_avg_pct": round(sum(overall) / len(overall), 2) if overall else None,
        "rules": rule_stats,
        "signals": sorted(graded, key=lambda g: -g["ts"])[:30],
        # Symbols whose price could not be trusted — surfaced rather than
        # silently dropped, so a delisted or typo'd ticker is visible.
        "ungraded": ungraded,
    }
