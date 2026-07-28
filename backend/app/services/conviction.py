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
import re
import threading
import time

from ..config import settings
from ..models.schemas import BreakoutCandidate, StockReport
from . import discovery, market_data, screener
from . import portfolio as pf_service

COOLDOWN_DAYS = 3
ACTIVE_HOURS = 48  # signals stay on the dashboard this long
_LOW_CASH_MIN = 250  # below this dry powder, "no cash to open a new position"

_FIRED_FILE = settings.PORTFOLIO_FILE.parent / "conviction_fired.json"
_NOTES_FILE = settings.PORTFOLIO_FILE.parent / "conviction_notes.json"
_lock = threading.Lock()


def _load(path) -> dict:
    # Always UTF-8; fall back to cp1252 for any legacy file written under the
    # Windows default so a stray em-dash byte can't corrupt the whole store.
    for enc in ("utf-8", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return {}


def _save(path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[conviction] persist failed: {exc!r}")


# ------------------------------------------------------------------- rules
# Rules RETIRED on backtest evidence (2026-07-27). The 5-year replay graded
# every rule at 20 sessions; these three lost money on large samples, and the
# reason is the same in all three: they sell weakness in quality names, and
# over this period weakness in quality names was bought.
#
#   trend-break      424 signals  -3.95% avg  profit factor 0.54
#   rsi-sell-zone    377 signals  -4.08% avg  profit factor 0.41
#   sharp-breakdown   69 signals -10.54% avg  profit factor 0.18
#
# (For a SELL, "effective" return is negated — so sharp-breakdown firing at
# -10.54% means price ROSE ~10.5% over the next 20 sessions on average. It
# was selling bottoms.)
#
# They are suppressed from FIRING, not deleted, and the backtest still
# replays them (see `include_retired`). Deleting the logic would destroy the
# only evidence that could ever justify bringing them back — and the record
# above is regime-dependent: a mega-cap AI book through a bull run. Re-check
# on the Learning sheet after a genuine drawdown before treating this as
# settled. Un-retire by removing the entry here.
RETIRED_RULES = frozenset({"trend-break", "rsi-sell-zone", "sharp-breakdown"})


def _detect(sym: str, ind, quote, held: bool, pl_pct, score: float,
            earn_days: int | None = None, *,
            include_retired: bool = False) -> list[dict]:
    """High bar on purpose: a slap that fires weekly is a slap; one that
    fires hourly is wallpaper. earn_days gates BUY signals — no new entries
    into a binary event.

    include_retired: the BACKTEST passes True so retired rules keep being
    measured. The live scan leaves it False so they never reach the client."""
    out: list[dict] = []
    # NEVER signal off fallback/mock data — a live fetch failing must not
    # produce a real slap on a stale price (AMD's mock anchor is $165 while
    # it trades at $519). Only live quotes can fire a conviction signal.
    if getattr(quote, "source", "live") == "mock":
        return out
    p = quote.price
    chg = quote.change_pct
    near_earnings = earn_days is not None and earn_days <= 2

    def add(side, rule, label):
        if side == "buy" and near_earnings:
            return  # never slap a buy 0-2 days before a report
        if rule in RETIRED_RULES and not include_retired:
            return  # lost money on the replay — measured, not fired
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

    # Momentum ignition — the SNDK pattern: a name already RIPPING on real
    # volume near its highs. Different animal from a coiled breakout; the
    # engine was blind to explosions in progress.
    if (ind.ret_5d_pct is not None and ind.ret_5d_pct >= 12
            and (ind.volume_ratio or 0) >= 1.5
            and (ind.pct_from_52w_high is None or ind.pct_from_52w_high >= -8
                 or (ind.ret_20d_pct or 0) >= 25)):
        add("buy", "momentum-ignition",
            f"Momentum ignition: +{ind.ret_5d_pct:.0f}% in 5 days on "
            f"{(ind.volume_ratio or 0):.1f}x volume")

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
def _enrich(sig: dict, facts: str, book_ctx: str = "", price=None) -> dict:
    """The advisor's DEFINITIVE call on a screened setup. The deterministic
    screen is a LEAD, not an order — the advisor can AGREE or OVERRULE it. It
    returns an `action`, stays consistent with the standing stance, and writes
    that stance back. The scan then SUPPRESSES any signal the advisor won't
    endorse, so a 'buy' screen the advisor reads as AVOID never reaches the
    client as a buying opportunity (the whole point: one call, no contradiction).
    """
    from . import advisor
    from . import stance as stance_service

    sym = sig["symbol"]
    fallback_action = "BUY" if sig["side"] == "buy" else "SELL"
    fallback = {
        "action": fallback_action,
        "headline": sig["label"],
        "what": ("Start / add to the position on this setup." if sig["side"] == "buy"
                 else "Reduce or exit the position on this signal."),
        "why": [sig["label"]],
        "entry": "", "size": "",
        "target": "Set targets from the 52-week high and ATR — advisor unavailable.",
        "stop": "Use the 200-day SMA as the invalidation level.",
    }
    if not settings.ADVISOR_ENABLED:
        return {**sig, **fallback}

    stable = stance_service.is_stable(sym, price)
    prior = stance_service.get(sym)
    lead = "potential BUY" if sig["side"] == "buy" else "potential SELL/exit"
    prompt = (
        f"{advisor._PERSONA}\n\nA screen flagged {sym} as a {lead} setup "
        f"(rule: {sig['label']}).\n\n{facts}\n\n{stance_service.block(sym, price)}"
        f"{book_ctx}\n\n"
        f"Give your DEFINITIVE call on {sym}. The screen is a LEAD, not an order "
        f"— AGREE only if you genuinely would act now. If {sym} is extended, "
        f"unconfirmed, or against your standing call, say HOLD or AVOID; do not "
        f"rubber-stamp a buy you don't believe in. Respond with ONLY JSON: "
        f'{{"action": one word BUY|ADD|HOLD|TRIM|SELL|AVOID, '
        f'"headline": under-10-word verdict, '
        f'"what": ONE sentence — the exact move, or why to stand down, '
        f'"entry": exact price/zone to act now (empty if no action now), '
        f'"size": dollar amount AND % of book, conviction-scaled (empty if none), '
        f'"target": concrete target price or "", '
        f'"stop": concrete invalidation price or "", '
        f'"why": array of 2-4 bullets citing the numbers}}. '
        f"NEVER say 'consider' or 'you could'. Be decisive."
    )
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return {**sig, **fallback}
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            action = str(obj.get("action") or fallback_action).strip().upper().split()[0]
            if action not in {"BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID"}:
                action = fallback_action
            # Sticky: nothing material moved -> keep the standing call, don't flip.
            if stable and prior:
                action = prior["action"]
            out = {**sig,
                   "action": action,
                   "headline": str(obj.get("headline") or sig["label"]),
                   "what": str(obj.get("what") or fallback["what"]),
                   "why": advisor._as_bullets(obj.get("why")) or [sig["label"]],
                   "entry": str(obj.get("entry") or ""),
                   "size": str(obj.get("size") or ""),
                   "target": str(obj.get("target") or ""),
                   "stop": str(obj.get("stop") or "")}
            if not (stable and prior):
                try:
                    stance_service.set_stance(
                        sym, action, headline=out["headline"], thesis=out["what"],
                        target=out["target"], stop=out["stop"], source="signal",
                        price=price)
                except Exception:
                    pass
            return out
        except json.JSONDecodeError:
            pass
    return {**sig, **fallback}


def market_active() -> bool:
    """US extended trading window: pre-market 7:00 through after-hours 20:00
    ET, weekdays. Holidays not modeled.

    The biggest runners gap up in pre-market on overnight news and stocks
    react after earnings post-close, so the watchdog covers the whole
    tradeable window — it only sleeps overnight (8pm-7am) and on weekends.
    Dashboard/briefs/advisor still work any time; only signal scanning pauses
    when nothing is tradeable."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return 7 * 60 <= mins < 20 * 60


# backwards-compat alias
market_open = market_active


# -------------------------------------------------------------------- scan
def scan() -> list[dict]:
    """Detect, enrich new signals, and return everything active (last 48h)."""
    with _lock:
        fired = _load(_FIRED_FILE)
        notes = _load(_NOTES_FILE)
        today = time.strftime("%Y-%m-%d")
        now = time.time()

        # Watchdog sleeps when nothing is tradeable (overnight/weekends): no
        # detection, no Claude enrichment, no pushes. Just return the still-
        # active recent signals so the dashboard/bell keep showing them.
        if not market_active():
            active = {k: v for k, v in notes.items()
                      if now - float(v.get("ts", 0)) < ACTIVE_HOURS * 3600}
            _save(_NOTES_FILE, active)
            return sorted(active.values(),
                          key=lambda s: float(s.get("ts", 0)), reverse=True)
        # Track pre-existing ids so we push ONLY newly-fired signals — one
        # buzz per new slap, never a re-ping of something already surfaced.
        known_ids = set(notes.keys())

        # Unify holdings + watchlist (full reports) and Discovery (light).
        items: list[tuple] = []
        book_ctx = ""
        low_cash = False  # no dry powder → skip not-owned + runner checks/enrichment
        # Standing preference, read outside the try so a config failure can
        # never leave it undefined further down. Defaults to the safe/quiet
        # behaviour: only signal on names actually in the book.
        try:
            owned_only = bool(
                pf_service.load_portfolio().get("signals_owned_only", True))
        except Exception:
            owned_only = True
        try:
            summary, reports = pf_service.portfolio_summary()
            book_val = summary.total_market_value
            dry = (summary.by_theme.get("Cash & Income", summary.cash)
                   if summary.by_theme else summary.cash)
            try:
                quiet = pf_service.load_portfolio().get("quiet_unowned_low_cash", True)
            except Exception:
                quiet = True
            # Effective dry powder = cash MINUS what's already queued to buy, so
            # committing cash to pins counts as spent even before it's executed.
            queued = 0.0
            try:
                from . import pins as pins_svc
                for p in pins_svc.list_pins():
                    if p.get("status") == "open" and re.match(r"^\W*(buy|add)\b", p.get("text", "").lower()):
                        mm = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", p.get("text", ""))
                        if mm:
                            queued += float(mm.group(1).replace(",", ""))
            except Exception:
                queued = 0.0
            effective_dry = max(0.0, dry - queued)
            # "effectively no cash to open a new position" — can't buy anything
            # meaningful, so runners/watchlist/discovery alerts are just noise +
            # wasted Claude spend. Owned names still get watched (sell/trim/add).
            low_cash = bool(quiet) and effective_dry < _LOW_CASH_MIN
            if book_val:
                book_ctx = (
                    f"CLIENT'S ACTUAL BOOK: ${book_val:,.0f} total (the WHOLE "
                    f"portfolio — never assume a generic $100k). Fractional shares "
                    f"are available: size in DOLLARS (any amount), fractional "
                    f"share count is fine, never round to whole shares. SIZE TO "
                    f"CONVICTION AND RISK — do not default to a timid cap: a "
                    f"tentative or extended/chase setup gets a small starter (a "
                    f"few % of book), but a HIGH-conviction, thesis-backed setup "
                    f"can justify a meaningful position (10-20%+). Recommend the "
                    f"size you genuinely believe is CORRECT and say why. Anchor "
                    f"size to the stop (wider stop = smaller size) so a stop-out "
                    f"is a loss the book can absorb; don't over-concentrate the "
                    f"whole book in one name; never exceed the cash/book available.")
            reports = reports + pf_service.watchlist_reports()
            for r in reports:
                items.append((r.symbol, r.indicators, r.quote,
                              r.market_value is not None, r.unrealized_pl_pct,
                              screener.breakout_score(r.indicators, r.quote),
                              r.theme, r.days_to_earnings))
            # Signals on names outside the book are alerts you can't act on and
            # wouldn't want to — and since the discovery universe went
            # market-wide (~190 tickers) they'd be constant. Discovery itself
            # and the advisor's scouting still see the whole market; this gates
            # the SLAP engine only.
            if not owned_only:
                for c in discovery.discover(min_score=0, limit=200)["results"]:
                    items.append((c.symbol, c.indicators, c.quote, False, None,
                                  c.score, c.theme, None))
        except Exception as exc:
            print(f"[conviction] scan data failed: {exc!r}")

        for sym, ind, quote, held, pl, score, theme, earn_days in items:
            if theme == "Cash & Income":
                # T-bill/cash funds drift up by design — RSI pins near 100
                # and every momentum rule misreads them. Never signal cash.
                continue
            if low_cash and not held:
                # No dry powder — a buy alert on a name you don't own is nothing
                # you can act on. Skip it (and its Claude enrichment) entirely.
                continue
            for sig in _detect(sym, ind, quote, held, pl, score, earn_days):
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
                enriched = _enrich(sig, _facts(sym, ind, quote, held, pl, score, theme),
                                   book_ctx, quote.price)
                # The advisor is the FINAL word. A screen 'buy' it reads as
                # HOLD/AVOID must NOT reach you as a buying opportunity — that's
                # the self-contradiction that broke trust. Suppress it (the
                # standing stance is still recorded, silently), and cooldown so
                # we don't re-ask every scan.
                action = str(enriched.get("action") or "").upper()
                endorses = ((sig["side"] == "buy" and action in ("BUY", "ADD")) or
                            (sig["side"] == "sell" and action in ("SELL", "TRIM", "AVOID")))
                fired[cool_key] = today
                if not endorses:
                    continue
                notes[sig_id] = enriched

        # Runner ignition: whole-market movers running NOW, caught EARLY. Each
        # is staged — 'igniting' (up ~7-25% on heavy volume, near highs, runway
        # left → a real momentum entry) vs 'extended' (already ran / faded → do
        # NOT chase, watch for a pullback). The stage drives the advisor's read
        # so the slap never says BUY on a name that already topped.
        try:
            from . import runner
            # Runner ignition is by definition a whole-market scan for names
            # you don't own, so owned-only silences it outright.
            for m in ([] if (low_cash or owned_only) else runner.igniting_movers()):
                sym = m["symbol"]
                cool_key = f"{sym}:runner-ignition"
                last = fired.get(cool_key)
                if last:
                    try:
                        days = (time.mktime(time.strptime(today, "%Y-%m-%d")) -
                                time.mktime(time.strptime(last, "%Y-%m-%d"))) / 86400
                    except ValueError:
                        days = COOLDOWN_DAYS
                    if days < COOLDOWN_DAYS:
                        continue
                cap_b = m["market_cap"] / 1e9
                stage = m.get("stage", "igniting")
                rvol = m.get("rvol")
                rvol_txt = f", {rvol:.0f}x avg volume" if rvol else ""
                sig_id = f"{cool_key}:{today}"
                if stage == "extended":
                    event = (
                        f"{sym} has ALREADY RUN +{m['change_pct']:.0f}% today"
                        f"{rvol_txt} (${cap_b:.1f}B cap) and is extended/fading off "
                        f"the high — the bulk of the move is likely done. Do NOT "
                        f"chase the top; only assess a pullback or a volume-backed "
                        f"continuation entry, else stand aside.")
                else:
                    event = (
                        f"{sym} is IGNITING — up +{m['change_pct']:.0f}% today"
                        f"{rvol_txt} at a ${cap_b:.1f}B cap, still near the highs "
                        f"with runway. This is an EARLY momentum entry (lottery-"
                        f"ticket size); give the exact entry, tiny size and a hard "
                        f"stop, or say to wait for the first pullback.")
                try:
                    from . import advisor
                    reco = advisor.recommend(sym, event, kind="runner")
                except Exception as exc:
                    print(f"[conviction] runner reco failed: {exc!r}")
                    reco = {}
                default_action = "AVOID" if stage == "extended" else "BUY"
                stage_tag = ("already ran +" if stage == "extended" else "igniting +")
                notes[sig_id] = {
                    "id": sig_id, "symbol": sym,
                    "side": "sell" if stage == "extended" else "buy",
                    "rule": "runner-ignition", "stage": stage,
                    "label": f"Live runner: {stage_tag}{m['change_pct']:.0f}% today",
                    "headline": reco.get("headline")
                    or (f"{sym} already ran +{m['change_pct']:.0f}% — don't chase"
                        if stage == "extended"
                        else f"{sym} igniting — +{m['change_pct']:.0f}% on volume"),
                    "what": reco.get("what")
                    or (f"{sym} ({m['name']}) up {m['change_pct']:.0f}% today at a "
                        f"${cap_b:.1f}B cap. Check float on the Runner Radar before "
                        f"sizing; lottery-ticket size only."),
                    "why": reco.get("why") or [
                        f"Up {m['change_pct']:.0f}% today on {m['volume']/1e6:.1f}M "
                        f"shares{rvol_txt} — real participation.",
                        f"${cap_b:.1f}B market cap — small enough to move fast.",
                    ],
                    "entry": reco.get("entry", ""), "size": reco.get("size", ""),
                    "target": reco.get("target", ""), "stop": reco.get("stop", ""),
                    "action": reco.get("action", default_action),
                    "price": m["price"], "theme": "Runner", "held": False,
                    "dismissed": False,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": now,
                }
                fired[cool_key] = today
        except Exception as exc:
            print(f"[conviction] runner ignition failed: {exc!r}")

        # Watchpoints ride the same scan: evaluate armed tripwires against
        # the readings we just gathered (zero AI cost on trigger).
        try:
            from . import watchpoints
            # Only live prices trigger watchpoints — a mock fallback price
            # must never fire a level alert.
            readings = {sym: (quote.price, ind.rsi)
                        for sym, ind, quote, *_ in items
                        if getattr(quote, "source", "live") != "mock"}
            for sig in watchpoints.check(readings):
                # A tripwire firing isn't the whole answer — "AVGO hit RSI 45"
                # is a trigger, not a decision. Run the portfolio-aware advisor
                # so the slap ends in an actual recommended action (may be HOLD).
                try:
                    from . import advisor
                    event = (f"Your watchpoint fired — {sig['label']}. "
                             f"Your note: '{sig['what']}'. Reading: "
                             f"{'; '.join(sig.get('why', []))}")
                    reco = advisor.recommend(sig["symbol"], event, kind="alert")
                    if reco:
                        sig["action"] = reco.get("action", sig.get("action"))
                        sig["headline"] = reco.get("headline") or sig["headline"]
                        sig["what"] = reco.get("what") or sig["what"]
                        sig["why"] = (reco.get("why") or []) + [
                            f"Your watchpoint: {sig['label']}."]
                        sig["entry"] = reco.get("entry", "")
                        sig["size"] = reco.get("size", "")
                        sig["target"] = reco.get("target", "")
                        sig["stop"] = reco.get("stop", "")
                except Exception as exc:
                    print(f"[conviction] watchpoint reco failed: {exc!r}")
                notes[sig["id"]] = sig
        except Exception as exc:
            print(f"[conviction] watchpoint check failed: {exc!r}")

        # Plan Watch: re-evaluate the client's STAGED plans (open pins) against
        # the tape — a staged sell that's now running gets a RECONSIDER slap
        # before it's blindly executed. Advisor decides if the premise changed.
        try:
            from . import planwatch
            price_by = {sym: quote.price for sym, ind, quote, *_ in items
                        if getattr(quote, "source", "live") != "mock"}
            for sig in planwatch.check(price_by):
                notes[sig["id"]] = sig
        except Exception as exc:
            print(f"[conviction] plan watch failed: {exc!r}")

        # Keep only the active window; prune the rest from the notes file.
        active = {k: v for k, v in notes.items()
                  if now - float(v.get("ts", 0)) < ACTIVE_HOURS * 3600}
        _save(_NOTES_FILE, active)
        _save(_FIRED_FILE, fired)

        # Grade everything later: record fire prices (idempotent).
        try:
            from . import scorecard
            for v in active.values():
                scorecard.record(v)
        except Exception as exc:
            print(f"[conviction] scorecard record failed: {exc!r}")

        # Push newly-fired signals to registered devices (the slap in your
        # pocket). Only ids that didn't exist before this scan.
        new_sigs = [v for k, v in active.items() if k not in known_ids]

    # outside the lock — network call shouldn't hold the scan mutex.
    # Only ACTIONS buzz the phone — "hey do this": a concrete BUY/ADD/TRIM/SELL,
    # or a watchpoint YOU armed hitting (your own action trigger). Analysis,
    # HOLD, AVOID and "already ran / don't chase" stay silent in the app and
    # roll into the daily briefs instead. This is the notification-fatigue fix.
    if new_sigs:
        try:
            from . import push
            for v in new_sigs:
                if _should_push(v):
                    push.send_signal(v)
        except Exception as exc:
            print(f"[conviction] push failed: {exc!r}")

    # A poll is also the heartbeat for the once-a-day morning brief / EOD recap.
    try:
        from . import summary
        summary.maybe_send_daily()
    except Exception as exc:
        print(f"[conviction] daily summary check failed: {exc!r}")

    out = sorted(active.values(), key=lambda s: float(s.get("ts", 0)), reverse=True)
    return out


_PUSH_ACTIONS = {"BUY", "ADD", "TRIM", "SELL"}


def _should_push(sig: dict) -> bool:
    """A signal earns a phone push only if it's an ACTION. A watchpoint you
    armed always pushes (it's your own trigger); everything else pushes only
    when the advisor's call is a concrete move, not HOLD/AVOID/watch."""
    if sig.get("rule") == "watchpoint":
        return True
    return str(sig.get("action") or "").strip().upper() in _PUSH_ACTIONS


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
