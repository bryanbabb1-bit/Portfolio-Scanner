"""Conviction signals — the "slap me in the face" engine.

Deterministic rules watch every holding, watchlist name and Discovery
candidate for STRONG buy/sell setups. Detection is pure math (zero AI
tokens). Only when a NEW signal fires does one Claude call (standard model
tier) write the what / why / target — then it's persisted, so repeat polls
and the phone cost nothing. A per-symbol-per-rule cooldown stops the same
setup from re-slapping every day.
"""
from __future__ import annotations

import json
import threading
import time

from ..config import settings
from ..models.schemas import BreakoutCandidate, StockReport
from . import discovery, market_data, screener
from . import portfolio as pf_service

COOLDOWN_DAYS = 3
ACTIVE_HOURS = 48  # signals stay on the dashboard this long

_FIRED_FILE = settings.PORTFOLIO_FILE.parent / "conviction_fired.json"
_NOTES_FILE = settings.PORTFOLIO_FILE.parent / "conviction_notes.json"
_lock = threading.Lock()


def _load(path) -> dict:
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        print(f"[conviction] persist failed: {exc!r}")


# ------------------------------------------------------------------- rules
def _detect(sym: str, ind, quote, held: bool, pl_pct, score: float) -> list[dict]:
    """High bar on purpose: a slap that fires weekly is a slap; one that
    fires hourly is wallpaper."""
    out: list[dict] = []
    p = quote.price
    chg = quote.change_pct

    def add(side, rule, label):
        out.append({"symbol": sym, "side": side, "rule": rule, "label": label})

    # ----- BUY -----
    # Momentum-style AND dip-style rules: momentum only fires in strong
    # tapes, so without the dip rules the engine reads as sell-biased in
    # every correction — exactly when a buyer wants ideas.
    if (held and ind.rsi is not None and ind.rsi <= 35
            and ind.sma200 and abs(p / ind.sma200 - 1) <= 0.05
            and ind.sma50 and ind.sma50 >= ind.sma200 * 0.97):
        add("buy", "oversold-at-support",
            "Oversold at the 200-day with the long-term trend intact")

    if (ind.trend == "uptrend" and ind.rsi is not None and ind.rsi <= 38
            and ind.pct_from_52w_high is not None
            and -20 <= ind.pct_from_52w_high <= -8
            and score >= 45):
        add("buy", "quality-dip",
            "Uptrend name on sale: oversold in the accumulation zone")

    if (ind.rsi is not None and ind.rsi <= 30 and chg >= 2
            and (ind.volume_ratio or 0) >= 1.5):
        add("buy", "washed-out-reversal",
            "Capitulation reversal: deeply oversold and bouncing on volume")

    # RSI buy zone with confirmation — RSI alone catches falling knives, so
    # the rest of the research must validate: long-term structure not broken,
    # not crashing today, and a composite score that says the setup has legs.
    if (not any(s["rule"] == "oversold-at-support" for s in out)
            and ind.rsi is not None and ind.rsi <= 32
            and ind.sma50 and ind.sma200
            and (ind.sma50 >= ind.sma200 * 0.95
                 or abs(p / ind.sma200 - 1) <= 0.08)
            and chg > -6 and score >= 35):
        add("buy", "rsi-buy-zone",
            "RSI in the buy zone with the broader setup confirming")

    # RSI momentum reclaim — the confirmation-style entry the advisor quotes
    # ("buy when it reclaims 45"): RSI crossed UP through 45 today after a
    # genuinely washed-out stretch, with long-term structure intact. This is
    # the conservative sibling of rsi-buy-zone (which buys the extreme).
    if (ind.rsi is not None and ind.rsi_prev is not None
            and ind.rsi >= 45 and ind.rsi_prev < 45
            and (ind.rsi_min_10d or 100) <= 35
            and ind.sma50 and ind.sma200
            and (ind.sma50 >= ind.sma200 * 0.95
                 or abs(p / ind.sma200 - 1) <= 0.08)):
        add("buy", "rsi-reclaim",
            "RSI reclaimed 45 after a washout — momentum turn confirmed")

    if (score >= 72 and ind.pct_from_52w_high is not None
            and ind.pct_from_52w_high >= -5
            and (ind.volume_ratio or 0) >= 1.3):
        add("buy", "breakout-triggering",
            "Breakout triggering: at highs on expanding volume")

    if not held and score >= 72:
        add("buy", "high-conviction-discovery",
            "New-name setup: breakout readiness in the top tier")

    # ----- SELL -----
    if ind.rsi is not None and ind.rsi >= 80 and (ind.volume_ratio or 0) >= 2:
        add("sell", "blowoff-top",
            "Blowoff conditions: extreme RSI on a volume spike")

    # RSI sell zone with confirmation, held names only — take-profit alert
    # when extended AND either volume or price-at-highs corroborates.
    if (held and not any(s["rule"] == "blowoff-top" for s in out)
            and ind.rsi is not None and ind.rsi >= 75
            and ((ind.volume_ratio or 0) >= 1.3
                 or (ind.pct_from_52w_high is not None
                     and ind.pct_from_52w_high >= -3))):
        add("sell", "rsi-sell-zone",
            "RSI in the sell zone on a held name — extended, consider taking profits")

    if (held and ind.sma200 and ind.sma50 and p < ind.sma200
            and ind.sma50 < ind.sma200 and chg <= -3):
        add("sell", "trend-break",
            "Trend break: under the 200-day in a death-cross regime and falling")

    if held and chg <= -8 and (ind.volume_ratio or 0) >= 1.5:
        add("sell", "sharp-breakdown",
            "Sharp high-volume breakdown — something changed")

    return out


def _facts(sym: str, ind, quote, held: bool, pl_pct, score: float,
           theme) -> str:
    pos = f"HELD position, unrealized P/L {pl_pct:+.1f}%" if held and pl_pct is not None \
        else ("HELD position" if held else "NOT held (candidate)")
    return (
        f"Symbol {sym} ({quote.name}) | Theme {theme} | {pos}\n"
        f"Price ${quote.price} ({quote.change_pct:+.2f}% today) | "
        f"Breakout score {score:.0f}/100\n"
        f"RSI {ind.rsi} | MACD {ind.macd}/{ind.macd_signal} | Trend {ind.trend}\n"
        f"SMA50/200: {ind.sma50}/{ind.sma200} | 52w high {ind.high_52w} "
        f"({ind.pct_from_52w_high}% away) | ATR {ind.atr} | "
        f"Volume {ind.volume_ratio}x avg"
    )


# -------------------------------------------------------------- enrichment
def _enrich(sig: dict, facts: str) -> dict:
    """One standard-tier Claude call to write the what/why/target."""
    from . import advisor

    side_word = "BUYING OPPORTUNITY" if sig["side"] == "buy" else "STRONG SELL SIGNAL"
    fallback = {
        "headline": sig["label"],
        "what": ("Consider adding / starting a position." if sig["side"] == "buy"
                 else "Consider reducing or exiting the position."),
        "why": [sig["label"]],
        "target": "Set targets from the 52-week high and ATR — advisor unavailable.",
        "stop": "Use the 200-day SMA as the invalidation level.",
    }
    if not settings.ADVISOR_ENABLED:
        return {**sig, **fallback}

    prompt = (
        f"{advisor._PERSONA}\n\nA high-conviction {side_word} rule just fired "
        f"for a client:\nRule: {sig['label']}\n\n{facts}\n\n"
        f"Write the alert. Respond with ONLY a JSON object, no markdown: "
        f'{{"headline": punchy alert headline under 10 words, '
        f'"what": one sentence — the exact action to take, '
        f'"why": array of 2-4 bullet strings citing the numbers, '
        f'"target": one sentence — the price target and its basis, '
        f'"stop": one sentence — the level that invalidates this}}. '
        f"Each bullet a single sentence under 22 words."
    )
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return {**sig, **fallback}
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return {**sig,
                    "headline": str(obj.get("headline") or sig["label"]),
                    "what": str(obj.get("what") or fallback["what"]),
                    "why": advisor._as_bullets(obj.get("why")) or [sig["label"]],
                    "target": str(obj.get("target") or ""),
                    "stop": str(obj.get("stop") or "")}
        except json.JSONDecodeError:
            pass
    return {**sig, **fallback}


# -------------------------------------------------------------------- scan
def scan() -> list[dict]:
    """Detect, enrich new signals, and return everything active (last 48h)."""
    with _lock:
        fired = _load(_FIRED_FILE)
        notes = _load(_NOTES_FILE)
        today = time.strftime("%Y-%m-%d")
        now = time.time()

        # Unify holdings + watchlist (full reports) and Discovery (light).
        items: list[tuple] = []
        try:
            _, reports = pf_service.portfolio_summary()
            reports = reports + pf_service.watchlist_reports()
            for r in reports:
                items.append((r.symbol, r.indicators, r.quote,
                              r.market_value is not None, r.unrealized_pl_pct,
                              screener.breakout_score(r.indicators, r.quote),
                              r.theme))
            for c in discovery.discover(min_score=0, limit=200)["results"]:
                items.append((c.symbol, c.indicators, c.quote, False, None,
                              c.score, c.theme))
        except Exception as exc:
            print(f"[conviction] scan data failed: {exc!r}")

        for sym, ind, quote, held, pl, score, theme in items:
            if theme == "Cash & Income":
                # T-bill/cash funds drift up by design — RSI pins near 100
                # and every momentum rule misreads them. Never signal cash.
                continue
            for sig in _detect(sym, ind, quote, held, pl, score):
                cool_key = f"{sym}:{sig['rule']}"
                last = fired.get(cool_key)
                if last:
                    try:
                        days = (time.mktime(time.strptime(today, "%Y-%m-%d")) -
                                time.mktime(time.strptime(last, "%Y-%m-%d"))) / 86400
                    except ValueError:
                        days = COOLDOWN_DAYS
                    if days < COOLDOWN_DAYS:
                        continue
                sig_id = f"{cool_key}:{today}"
                sig.update({
                    "id": sig_id,
                    "price": quote.price,
                    "theme": theme,
                    "held": held,
                    "dismissed": False,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ts": now,
                })
                enriched = _enrich(sig, _facts(sym, ind, quote, held, pl, score, theme))
                notes[sig_id] = enriched
                fired[cool_key] = today

        # Watchpoints ride the same scan: evaluate armed tripwires against
        # the readings we just gathered (zero AI cost on trigger).
        try:
            from . import watchpoints
            readings = {sym: (quote.price, ind.rsi)
                        for sym, ind, quote, *_ in items}
            for sig in watchpoints.check(readings):
                notes[sig["id"]] = sig
        except Exception as exc:
            print(f"[conviction] watchpoint check failed: {exc!r}")

        # Keep only the active window; prune the rest from the notes file.
        active = {k: v for k, v in notes.items()
                  if now - float(v.get("ts", 0)) < ACTIVE_HOURS * 3600}
        _save(_NOTES_FILE, active)
        _save(_FIRED_FILE, fired)

    out = sorted(active.values(), key=lambda s: float(s.get("ts", 0)), reverse=True)
    return out


def dismiss(sig_id: str | None = None) -> int:
    """Hide a signal (or all, when sig_id is None) from the popup and strip.

    Dismissal is per signal id — a NEW fire (different rule, or the same rule
    after its cooldown) mints a new id and pops again."""
    with _lock:
        notes = _load(_NOTES_FILE)
        changed = 0
        for k, v in notes.items():
            if (sig_id is None or k == sig_id) and not v.get("dismissed"):
                v["dismissed"] = True
                changed += 1
        if changed:
            _save(_NOTES_FILE, notes)
    return changed


def demo_signal() -> dict:
    """A canned signal for previewing the alert UI — never persisted."""
    return {
        "id": "DEMO:preview:0000-00-00",
        "symbol": "NVDA", "side": "buy", "rule": "demo", "held": True,
        "label": "Oversold at the 200-day with the long-term uptrend intact",
        "headline": "NVDA at trend support — add zone",
        "what": "Add to NVDA in the $190-193 zone while the 200-day holds.",
        "why": [
            "RSI 31 is the most oversold reading since the April low.",
            "Price is 1.2% above the rising 200-day SMA at $190.73.",
            "Golden-cross regime intact — pullback, not breakdown.",
        ],
        "target": "First target $215 (the 50-day), then $229 — the June high.",
        "stop": "A daily close below $187 invalidates the setup.",
        "price": 193.4, "theme": "AI Infrastructure",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
    }
