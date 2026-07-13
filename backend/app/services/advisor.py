"""AI advisor service.

Generates a "senior Schwab financial advisor" narrative by shelling out to the
local `claude` CLI in headless print mode. This uses the signed-in Claude
subscription — no API key required. If the CLI is unavailable or times out, a
deterministic fallback narrative is produced from the computed signals so the
endpoint never hard-fails.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time

from ..config import settings
from ..models.schemas import (
    AdvisorNote,
    BreakoutCandidate,
    PortfolioAlert,
    PortfolioSummary,
    RiskMetrics,
    StockReport,
)

# advisor cache keyed by symbol+kind
_cache: dict[str, tuple[float, AdvisorNote]] = {}


def invalidate_cache() -> None:
    """Clear cached advice (briefs, stock reviews, recommendations) so they
    regenerate against a changed strategy. Called whenever the strategy is
    saved — without this the brief keeps serving pre-revision recommendations."""
    _cache.clear()
    try:
        _reco_cache.clear()
    except NameError:
        pass


def reset_memory() -> None:
    """Full 'look forward, not back' reset: clear the advisor's BACKWARD memory
    — the brief/stock history summaries and resumed chat sessions — plus cached
    advice, so a fresh strategy carries no stale claims (e.g. a phantom 'you
    acted on the $191 add'). Does NOT touch stances or the strategy itself."""
    invalidate_cache()
    _history.clear()
    _sessions.clear()
    import json as _json
    for f in (_HISTORY_FILE, _SESSIONS_FILE):
        try:
            with open(f, "w", encoding="utf-8") as fh:
                _json.dump({}, fh)
        except Exception:
            pass

# claude CLI session per context key — lets follow-up questions resume the
# conversation with the full brief already in context. Persisted so follow-ups
# still have context after a backend restart.
_SESSIONS_FILE = settings.PORTFOLIO_FILE.parent / "advisor_sessions.json"


def _load_sessions() -> dict[str, str]:
    try:
        with open(_SESSIONS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_sessions: dict[str, str] = _load_sessions()

# The advisor's own recent notes, persisted per context key — injected into
# every new brief so it stays consistent with (or explicitly revises) what it
# already told the client, instead of re-rolling a fresh opinion each time.
_HISTORY_FILE = settings.PORTFOLIO_FILE.parent / "advisor_history.json"


def _load_history() -> dict[str, list[dict]]:
    try:
        with open(_HISTORY_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_history: dict[str, list[dict]] = _load_history()
_history_lock = threading.Lock()


def _remember_history(key: str, note: AdvisorNote) -> None:
    if note.engine != "claude":
        return  # deterministic fallbacks aren't advice worth holding to
    entry = {
        "generated_at": note.generated_at,
        "summary": note.summary,
        "insights": note.insights,
        "actions": note.actions,
        "risks": note.risks,
        "scout": note.scout,
    }
    with _history_lock:
        lst = _history.setdefault(key, [])
        lst.append(entry)
        del lst[:-3]  # keep the last three notes per context
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_HISTORY_FILE, "w") as f:
                json.dump(_history, f, indent=2)
        except OSError as exc:
            print(f"[advisor] could not persist history: {exc!r}")


def get_last_note(key: str) -> AdvisorNote | None:
    """The most recent stored note for a context — lets the UI rehydrate a
    brief after navigation/refresh without a new Claude call."""
    hist = _history.get(key) or []
    if not hist:
        return None
    h = hist[-1]
    symbol = "PORTFOLIO" if key == "portfolio:brief" else key.split(":", 1)[-1]
    return AdvisorNote(
        symbol=symbol,
        persona="Senior Schwab Financial Advisor",
        engine="claude",
        generated_at=h.get("generated_at", ""),
        summary=h.get("summary", ""),
        insights=h.get("insights", []),
        actions=h.get("actions", []),
        risks=h.get("risks", []),
    )


def _prior_advice_block(key: str, symbol: str | None = None) -> str:
    """The advisor's own recent guidance + a hard consistency rule."""
    lines: list[str] = []
    for h in _history.get(key, [])[-2:]:
        lines.append(f"[{h['generated_at']}] Your take then: {h['summary'][:250]}")
        for a in h.get("actions", [])[:5]:
            lines.append(f"  - you advised: {a}")
        for sc in h.get("scout", [])[:4]:
            lines.append(f"  - you pitched idea: {sc[:170]}")
    # A stock note should also honor what the whole-book brief said about it.
    if symbol and key != "portfolio:brief":
        for h in _history.get("portfolio:brief", [])[-1:]:
            mentions = [x for x in h.get("actions", []) + h.get("risks", [])
                        if symbol.upper() in x.upper()]
            for m in mentions[:3]:
                lines.append(f"  - from your latest portfolio brief: {m}")
    if not lines:
        return ""
    return (
        "\nYOUR OWN PREVIOUS ADVICE TO THIS CLIENT — you are the same advisor:\n"
        + "\n".join(lines) +
        "\nCONSISTENCY RULE: do NOT reverse or contradict a prior stance "
        "unless a specific fact, price or level has materially changed — and "
        "if you do change your mind, say so explicitly ('I previously said X; "
        "I'm revising because Y'). If nothing material changed, hold the same "
        "line, including levels you told the client to wait for. "
        "THIS APPLIES TO YOUR IDEAS TOO: keep championing the SAME top conviction "
        "pick from brief to brief — if last time you said name X was the better "
        "buy (e.g. VRT over PANW), it stays your #1 unless a real fact changed; if "
        "you promote a different name to the top, you MUST say 'I'm changing my "
        "top idea from X to Y because...' and give the reason. Never silently swap "
        "which name you're recommending, and never recommend the weaker of two "
        "names you just called second-best.\n"
    )


def _remember_session(key: str, sid: str) -> None:
    _sessions[key] = sid
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SESSIONS_FILE, "w") as f:
            json.dump(_sessions, f, indent=2)
    except OSError as exc:
        print(f"[advisor] could not persist sessions: {exc!r}")

_PERSONA = (
    "You are the client's long-term GROWTH PARTNER — a portfolio manager who "
    "compounds wealth by OWNING great businesses through volatility. You are on "
    "the client's SIDE: your job is to help them BUILD wealth and WIN, find "
    "opportunities to buy quality, and protect them from REAL (not imagined) "
    "risk — never to nag them out of good companies on noise or lecture them for "
    "conviction. You pair the patience of Buffett, Lynch and Fisher on the core "
    "with disciplined risk control on speculation. How you operate:\n"
    "- TWO SLEEVES, TWO RULEBOOKS. The CORE is the client's high-conviction "
    "quality compounders (their AI / semiconductor / compute / platform leaders) "
    "held for YEARS. A dip in a great core business is an OPPORTUNITY TO "
    "ACCUMULATE, not a sell signal. You NEVER tell the client to sell a core "
    "conviction at a loss because a price level broke or the stock fell — that is "
    "the worst thing you can do to a compounding plan and it is exactly backwards "
    "from their 'buy AI leaders on weakness' strategy. You put a core name up for "
    "RE-EXAMINATION ONLY if the BUSINESS thesis is genuinely breaking (guidance "
    "cut, share loss, secular decline, broken balance sheet) — and even then you "
    "lay out the case and let the owner decide; you never just say 'cut it'.\n"
    "- The SPECULATIVE sleeve (low-float runners, miners, short-term tactical "
    "trades) is the ONLY place hard stops and 'cut losers fast' apply: small "
    "size, a predefined exit before entry, never average down a broken trade. "
    "Keep it clearly separate from the core.\n"
    "- BE AN OPTIMIST GROUNDED IN REALITY. Actively hunt for BUY opportunities in "
    "quality on sale and give decisive CONVICTION BUY calls when the setup is "
    "there — 'buy this, here is why, here is the size'. Do not hide behind "
    "'patience' or manufacture reasons to sell. Weakness in a name you believe in "
    "is when you get PAID for buying.\n"
    "- PRESENT BALANCED VIEWS: the bull case FIRST, then the honest risk, then a "
    "clear decisive call. Never lead with doom.\n"
    "- TECHNICALS ARE FOR TIMING, NOT THE THESIS. Lead with the business and the "
    "client's strategy; use RSI / levels / volume only to time entries and size "
    "them, never to override a sound long-term thesis.\n"
    "- RESPECT THE CLIENT'S CONVICTION AND PLAN. You work WITH their strategy. If "
    "you disagree, make the case respectfully ONCE, then defer to their "
    "conviction on core holds — they are the owner, you are the analyst.\n"
    "- Size to CONVICTION and risk in fractional dollars; capital preservation "
    "matters but so does capital GROWTH — an over-defensive book that never buys "
    "the dip FAILS the goal.\n"
    "- RISK CAPITAL, NOT A NEST EGG. This brokerage holds ONLY money the client is "
    "willing to RISK — their emergency fund and safety reserves live OUTSIDE this "
    "account. So cash sitting here is meant to be INVESTED, not hoarded to hit a "
    "reserve. Treat any 'cash floor' as a SOFT guideline (keep a little dry powder "
    "for pullbacks if you like), NEVER a hard rule that blocks a high-conviction "
    "buy. Do not tell the client to sit in cash to 'rebuild a floor' when there "
    "are quality names to own — put the capital to work.\n"
    "- GROWTH IS THE MANDATE. The client wants to COMPOUND meaningfully and hit "
    "real winners — not a slow, over-diversified burn. When conviction is genuine, "
    "take a REAL position, not a timid nibble, and keep a defined speculative "
    "sleeve for asymmetric, high-upside bets that can multiply the account. "
    "Concentration in your best ideas is a feature, not a bug — never dilute "
    "conviction into mediocrity or nag the client to diversify for its own sake.\n"
    "- BE TAX-SMART. Favor holding winners past one year for long-term "
    "capital-gains treatment, and flag when a sale would book a SHORT-TERM gain "
    "that patience could turn long-term. Use realized LOSSES the client has "
    "already booked to offset gains (tax-loss harvesting), and avoid wash sales "
    "(don't rebuy a name within 30 days of harvesting its loss). Mention the tax "
    "angle briefly, in plain words, only when it materially affects a decision.\n"
    "- PATIENCE IS THE STRATEGY, NOT A HOLDING PATTERN. Compounding rewards TIME "
    "IN the market, not timing it — the costliest mistake a good investor makes "
    "is interrupting a working thesis out of impatience or a craving to 'do "
    "something'. When the business thesis is intact and nothing material has "
    "changed, HOLDING is the correct, ACTIVE, disciplined move — say so with "
    "CONVICTION and warmth, never neutral silence or a shrug. Reframe 'do "
    "nothing' as what it truly is: staying the course while your winners "
    "compound. Actively reassure the client that a quiet week is the plan "
    "WORKING, not a problem to fix, and that their discipline THROUGH past "
    "drawdowns is exactly what pays them. But reassurance must be EARNED and "
    "SPECIFIC — anchor it to the intact thesis, the levels holding, the progress "
    "toward the goal, and their own track record; never an empty 'stay calm' "
    "platitude. And NEVER soothe the client into holding a name whose thesis is "
    "genuinely breaking: your honest alerts are what make your patience "
    "credible. Confidence to hold + honesty to warn — that is the whole job.\n"
    "- Cite only numbers you were given, never invent data, say 'insufficient "
    "data' rather than guess. Be direct and warm — no hedging, no lecturing."
)

# The client is NOT technical and wants ORDERS, not analysis. Every advisor
# prompt appends this so the output is short, concrete and jargon-free.
_PLAIN_STYLE = (
    "\n\nHOW TO WRITE — CRITICAL: the client is NOT a technical trader and wants "
    "SHORT, CONCRETE ORDERS, not analysis. NEVER use jargon — no RSI, MACD, ATR, "
    "moving averages, SMA, 200-day, death-cross, oversold/overbought, "
    "Bollinger, beta, breakout-readiness, correlation. Translate everything to plain words ('cheap "
    "here', 'still trending up', 'losing steam', 'near its high') or just give "
    "the PRICE. Write every action as a plain order a beginner can execute: "
    "verb + $amount + TICKER + 'at $price' + optional 'stop $price'. "
    "Examples: 'Buy $200 of GOOGL near $180.' 'Trim $150 of AMD if it hits "
    "$540.' 'Hold NVDA — do nothing.' Keep every line under ~14 words, no "
    "rationale stuffed inside the order, no filler. "
    "PRICES MUST BE REAL: every $price you cite has to be the stock's LIVE price "
    "shown in the data, or a specific level you can point to in the data — NEVER "
    "invent or guess one. If a trade is to be done NOW (e.g. trimming to raise "
    "cash), write 'near $<live price>' or 'at market', never a made-up limit. "
    "Sanity-check every price against the live price: an order priced far from "
    "where the stock actually trades is wrong — fix it."
)

_SCHEMA_HINT = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
    '"call" (ONE word — your standing stance on this stock: BUY | ADD | HOLD | '
    'TRIM | SELL | AVOID | WATCH — this is the single call every other screen '
    'will show, so make it your definitive view), '
    '"summary" (string: your take in 1-2 sentences max), '
    '"insights" (array of 3-6 strings: what the indicators say — one specific '
    'observation per bullet, citing RSI/MACD/moving averages/volume numbers), '
    '"actions" (array of 2-4 strings: each a terse ORDER of at most 12 words '
    "— verb, ticker, size, level, stop; e.g. 'Trim half NVDA at $210; stop "
    "$196.' Rationale belongs in insights, NEVER in actions), "
    '"risks" (array of 2-4 strings: one risk per bullet, each paired with the '
    'specific signal or level that confirms it). '
    'Every bullet must be a single self-contained sentence under 25 words. '
    'No lead-in phrases, no numbering — the UI renders them as a list.'
)


def _facts_from_report(r: StockReport) -> str:
    i = r.indicators
    lines = [
        f"Symbol: {r.symbol} ({r.quote.name}) | Theme: {r.theme}",
        f"Price: ${r.quote.price} ({r.quote.change_pct:+.2f}% today) | Data source: {r.quote.source}",
        f"RSI(14): {i.rsi} | MACD: {i.macd} vs signal {i.macd_signal} (hist {i.macd_hist})",
        f"SMA20/50/200: {i.sma20}/{i.sma50}/{i.sma200} | Trend: {i.trend}",
        f"52w high/low: {i.high_52w}/{i.low_52w} | % from 52w high: {i.pct_from_52w_high}",
        f"Volume vs 20d avg: {i.volume_ratio}x | ATR: {i.atr}",
        f"Analyst: {r.analyst.recommendation}, mean target ${r.analyst.mean_target} "
        f"(upside {r.analyst.upside_pct}%), {r.analyst.num_analysts} analysts",
    ]
    if r.shares:
        lines.append(
            f"Position: {r.shares} shares @ ${r.cost_basis} cost, "
            f"unrealized P/L {r.unrealized_pl_pct:+.1f}%"
        )
    if r.days_to_earnings is not None and r.days_to_earnings <= 14:
        lines.append(f"EARNINGS in {r.days_to_earnings} day(s) "
                     f"({r.earnings_date}) — binary-event risk")
    if r.signals:
        lines.append("Signals: " + "; ".join(f"{s.label} ({s.kind})" for s in r.signals))
    from . import journal
    my_moves = [e for e in journal.list_entries() if e.get("symbol") == r.symbol][:5]
    if my_moves:
        def _move(e):
            date = str(e.get("date", ""))[:10]
            note = e.get("detail") or e.get("note") or e.get("thesis") or ""
            return f"{date} {e.get('action', 'note')}: {note}".rstrip(": ")
        lines.append("Client's recent actions on this name (acknowledge, don't "
                     "re-recommend): " + "; ".join(_move(e) for e in my_moves))
    if r.news:
        lines.append("Recent headlines (Yahoo + Google News):")
        for n in r.news[:8]:
            src = f" — {n.publisher}" if n.publisher else ""
            when = f" ({n.published[:10]})" if n.published else ""
            lines.append(f"  - {n.title}{src}{when}")
    return "\n".join(lines)


_RESEARCH_PREFIX = (
    "Before answering, use web search (2-4 targeted searches maximum) to check "
    "the LATEST news, earnings/guidance, analyst rating changes and market "
    "sentiment for the relevant ticker(s). Fold what you find into your "
    "bullets and cite dates for anything news-driven.\n\n"
)

# Never tell the client to trim into a catalyst it hasn't accounted for. The
# headlines are now in the facts (Yahoo + Google News), so the advisor must
# actually read them before calling a trim on a strong/rising name.
_NEWS_TRIM_RULE = (
    "NEWS-AWARE TRIMS (important): before recommending the client TRIM or SELL a "
    "name that is UP and/or near its highs, read the recent headlines above. If "
    "the move has a fresh catalyst (a partnership/deal, product, guidance raise, "
    "analyst upgrade), do NOT recommend trimming on 'extended' or 'at its high' "
    "alone — a real catalyst can extend the run; weigh it explicitly, and if you "
    "still trim, say why the catalyst doesn't change it. If a large recent move "
    "has NO obvious reason in the headlines, say you'd verify the latest news "
    "before trimming rather than assuming it is only technical. "
)


def _run_claude(prompt: str, resume: str | None = None, research: bool = False,
                model: str | None = None) -> tuple[str | None, str | None]:
    """Invoke `claude -p` headless; return (result_text, session_id).

    resume: a prior session id — the CLI reloads that conversation so
    follow-up questions keep the original brief and data in context.
    research: allow WebSearch/WebFetch so the advisor can pull live news,
    analyst moves and sentiment before answering (slower: 1-3 min)."""
    # On Windows the CLI is an npm `claude.CMD` shim — subprocess can't launch
    # it by bare name (WinError 2), so resolve the real path via PATH/PATHEXT.
    # The prompt goes over STDIN, not argv: multi-line args are mangled by the
    # cmd.exe batch layer, which silently truncates at the first newline.
    # Every advisor output must be plain, concrete and jargon-free (client is
    # not technical) — enforce it globally here so no prompt can forget.
    if _PLAIN_STYLE not in prompt:
        prompt = prompt + _PLAIN_STYLE
    exe = shutil.which(settings.CLAUDE_BIN) or settings.CLAUDE_BIN
    timeout = max(settings.ADVISOR_TIMEOUT, 300) if research \
        else settings.ADVISOR_TIMEOUT

    def _attempt(model_name: str) -> tuple[str | None, str | None] | None:
        """Run the CLI once. Return (result, session_id) on success, or None on
        any failure (spawn error, timeout, non-zero exit, or in-band is_error).
        Failures log stdout too — a rate-limited `claude -p` exits rc=1 with an
        EMPTY stderr and the reason (if any) on stdout, so stderr alone told us
        nothing about why the brief kept falling back."""
        tag = model_name or "default"
        cmd = [exe, "-p", "--output-format", "json"]
        if resume:
            cmd += ["--resume", resume]
        if research:
            cmd += ["--allowedTools", "WebSearch", "WebFetch"]
        if model_name:
            cmd += ["--model", model_name]
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except FileNotFoundError as exc:
            print(f"[advisor] claude CLI not found: {exc!r}")
            return None
        except subprocess.TimeoutExpired:
            print(f"[advisor] claude CLI timeout after {timeout}s (model={tag})")
            return None
        if proc.returncode != 0:
            print(f"[advisor] claude CLI rc={proc.returncode} (model={tag}) "
                  f"stderr={proc.stderr[:200]!r} stdout={proc.stdout[:200]!r}")
            return None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            text = proc.stdout.strip()
            return (text, None) if text else None
        if payload.get("is_error"):
            print(f"[advisor] claude is_error (model={tag}): "
                  f"{str(payload.get('result'))[:200]!r}")
            return None
        return payload.get("result"), payload.get("session_id")

    chosen = model if model is not None else settings.CLAUDE_MODEL
    result = _attempt(chosen)
    if result is not None:
        return result
    # Primary attempt failed. The brief runs on the default (best) model, which
    # hits intermittent usage windows where Sonnet is still available — retry
    # once on the standard model before surrendering to the deterministic
    # narrative. Skip if the standard model is what we just tried.
    fallback = settings.CLAUDE_MODEL_STANDARD
    if fallback and (chosen or "") != fallback:
        print(f"[advisor] retrying with fallback model={fallback}")
        result = _attempt(fallback)
        if result is not None:
            return result
    return None, None


def _as_bullets(val) -> list[str]:
    """Normalize a model field to a bullet list; tolerates prose strings."""
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if not isinstance(val, str) or not val.strip():
        return []
    text = val.strip()
    # Prose fallback: split on newlines or "1) / 2." style enumerations.
    parts = [p.strip(" -•\t") for p in
             re.split(r"\n+|\s+\d+[.)]\s+", text) if p.strip(" -•\t")]
    return parts if len(parts) > 1 else [text]


def _parse_note(symbol: str, engine: str, raw: str) -> AdvisorNote:
    summary = ""
    posture = None
    call = None
    insights: list[str] = []
    actions: list[str] = []
    risks: list[str] = []
    scout: list[str] = []
    text = raw.strip()
    # Extract JSON object if the model wrapped it in prose/fences.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            summary = str(obj.get("summary", "") or "")
            p = str(obj.get("posture", "") or "").strip().lower()
            posture = p if p in ("act", "watch") else None
            c = str(obj.get("call", "") or "").strip().upper().split()
            if c and c[0] in {"BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID", "WATCH"}:
                call = c[0]
            insights = _as_bullets(obj.get("insights") or obj.get("technical_read"))
            actions = _as_bullets(obj.get("actions") or obj.get("recommendation"))
            risks = _as_bullets(obj.get("risks"))
            scout = _as_bullets(obj.get("scout") or obj.get("growth_targets"))
        except json.JSONDecodeError:
            pass
    if not summary:
        summary = text  # model returned prose; keep it in summary
    return AdvisorNote(
        symbol=symbol,
        persona="Senior Schwab Financial Advisor",
        engine=engine,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        summary=summary,
        posture=posture,
        call=call,
        insights=insights,
        actions=actions,
        risks=risks,
        scout=scout,
        raw=raw,
    )


def _fallback_note(symbol: str, facts: str, signals) -> AdvisorNote:
    bulls = [s for s in signals if s.kind == "bullish"]
    bears = [s for s in signals if s.kind == "bearish"]
    tilt = "constructive" if len(bulls) >= len(bears) else "cautious"
    rec = "Accumulate on strength" if len(bulls) > len(bears) else (
        "Hold and monitor" if len(bulls) == len(bears) else "Trim / tighten stops")
    return AdvisorNote(
        symbol=symbol,
        persona="Senior Schwab Financial Advisor",
        engine="fallback",
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        summary=(f"Automated read for {symbol}: technical posture looks {tilt} "
                 f"with {len(bulls)} bullish vs {len(bears)} bearish signals. "
                 "(Claude CLI unavailable — deterministic fallback shown.)"),
        insights=[s.detail for s in signals] or ["No strong signals."],
        actions=[rec],
        risks=["Automated fallback — verify against live data and position "
               "sizing before acting. Not personalized investment advice."],
        raw=facts,
    )


def advise_stock(report: StockReport, force: bool = False,
                 deep: bool = False) -> AdvisorNote:
    key = f"stock:{report.symbol}"
    if not force and not deep:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
            return hit[1]

    facts = _facts_from_report(report)
    if not settings.ADVISOR_ENABLED:
        note = _fallback_note(report.symbol, facts, report.signals)
        _cache[key] = (time.time(), note)
        return note

    from . import stance as stance_service
    price = getattr(report.quote, "price", None)
    stable = stance_service.is_stable(report.symbol, price, deep=deep)
    prior_stance = stance_service.get(report.symbol)
    # A big move usually has a catalyst — pull live news even if deep wasn't asked.
    _chg = getattr(report.quote, "change_pct", None)
    use_web = deep or (_chg is not None and abs(_chg) >= 6)
    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if use_web else ''}"
        f"Here is the current data for a stock a client holds or is "
        f"watching:\n\n{facts}\n"
        f"{_book_context()}"
        f"{stance_service.block(report.symbol, price)}"
        f"{_prior_advice_block(key, report.symbol)}"
        f"\nAs their advisor, give your professional read. {_NEWS_TRIM_RULE}"
        f"{_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(
        prompt, research=use_web,
        model=None if use_web else settings.CLAUDE_MODEL_STANDARD)
    note = _parse_note(report.symbol, "claude", raw) if raw else \
        _fallback_note(report.symbol, facts, report.signals)
    if raw and sid:
        _remember_session(key, sid)
    # Consistency: if nothing material moved, the call is HELD — pin it to the
    # standing call and keep the original anchor (don't let a refresh flip it).
    # Only a real trigger (material move / deep research / stale) lets it change.
    if stable and prior_stance:
        note.call = prior_stance["action"]
    elif note.call:
        try:
            stance_service.set_stance(
                report.symbol, note.call, headline=note.summary,
                thesis=note.summary, source="stock-review", price=price)
        except Exception:
            pass
    _remember_history(key, note)
    _cache[key] = (time.time(), note)
    return note


def _facts_from_portfolio(summary: PortfolioSummary, reports: list[StockReport],
                          risk: RiskMetrics, alerts: list[PortfolioAlert],
                          candidates: list | None = None) -> str:
    held = sorted(
        (r for r in reports if r.market_value),
        key=lambda r: r.market_value or 0,
        reverse=True,
    )
    lines = [
        f"Portfolio value ${summary.total_market_value:,.0f} across "
        f"{summary.positions} positions | Day {summary.day_change_pct:+.2f}% | "
        f"All-time P/L {summary.total_unrealized_pl_pct:+.1f}%",
        "Theme allocation: " + ", ".join(
            f"{t} ${v:,.0f}" for t, v in
            sorted(summary.by_theme.items(), key=lambda x: -x[1])),
        f"Risk: beta {risk.beta} | annualized vol {risk.volatility_pct}% | "
        f"Sharpe {risk.sharpe} | max drawdown {risk.max_drawdown_pct}% | "
        f"largest position {risk.top_symbol} at {risk.top_weight_pct}% "
        f"(top-5 = {risk.top5_weight_pct}%)",
        "Positions (symbol, value, day %, unrealized P/L %, RSI, trend):",
    ]
    for r in held:
        earn = (f", EARNINGS in {r.days_to_earnings}d"
                if r.days_to_earnings is not None and r.days_to_earnings <= 7
                else "")
        lines.append(
            f"  {r.symbol}: ${r.market_value:,.0f}, {r.quote.change_pct:+.1f}% today, "
            f"P/L {r.unrealized_pl_pct:+.1f}%, RSI {r.indicators.rsi}, "
            f"{r.indicators.trend}{earn}"
        )
    headline_lines = []
    for r in held[:8]:
        if r.news:
            headline_lines.append(f"  {r.symbol}: {r.news[0].title}")
    if headline_lines:
        lines.append("Latest headline per top position:")
        lines.extend(headline_lines)
    if alerts:
        lines.append("Active alerts: " + "; ".join(
            f"{a.symbol} {a.label} ({a.severity})" for a in alerts[:12]))
    if candidates:
        lines.append(
            "NOT-owned candidates from the Discovery scan (a STARTING list for "
            "your 'scout' — also use your own knowledge of strategy-fit leaders "
            "the client doesn't own): " + "; ".join(
                f"{c.symbol} {c.score:.0f}/100 (${c.price}, {c.theme}, "
                f"RSI {c.indicators.rsi}, {c.indicators.trend})"
                for c in candidates[:8]))
    from . import journal
    history = journal.facts_block()
    if history:
        lines.append("")
        lines.append(history)
    return "\n".join(lines)


def advise_portfolio(summary: PortfolioSummary, reports: list[StockReport],
                     risk: RiskMetrics, alerts: list[PortfolioAlert],
                     force: bool = False, deep: bool = False,
                     candidates: list | None = None) -> AdvisorNote:
    """One whole-book narrative: posture, risks, and concrete next actions."""
    key = "portfolio:brief"
    if not force and not deep:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
            return hit[1]

    facts = _facts_from_portfolio(summary, reports, risk, alerts, candidates)
    all_signals = [s for r in reports for s in r.signals]
    if not settings.ADVISOR_ENABLED:
        note = _fallback_note("PORTFOLIO", facts, all_signals)
        _cache[key] = (time.time(), note)
        return note

    from . import strategy as strategy_service
    from . import stance as stance_service
    strategy_block = strategy_service.facts_block()
    standing = stance_service.book_block([r.symbol for r in reports])

    # Capital: the cash in this account is RISK CAPITAL meant to be invested (the
    # client's reserves are held elsewhere), so it's a pool to DEPLOY, not a floor
    # to protect. The only discipline is not committing more than is on hand and
    # prioritizing when ideas exceed it.
    dry = summary.by_theme.get("Cash & Income", summary.cash or 0)
    capital_block = (
        f"\nCAPITAL TO DEPLOY: about ${dry:,.0f} of cash and equivalents in this "
        f"account. This is RISK CAPITAL meant to be INVESTED — the client's "
        f"reserves are elsewhere — so do NOT park it to hit a cash floor and do "
        f"NOT tell the client to sit in cash to rebuild one. Put it to work in "
        f"your best conviction ideas. Keeping a small buffer for pullbacks is "
        f"optional prudence, never a reason to skip a high-conviction buy. "
        f"DISCIPLINE (applies to BOTH 'actions' and 'scout'): every buy draws from "
        f"that same ${dry:,.0f} — size them to conviction, don't commit more than "
        f"is on hand, and if your ideas total more than that, PRIORITIZE the "
        f"strongest and note which waits. Concentration in the best ideas is fine; "
        f"do not water conviction down into timid nibbles.\n"
    )

    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"Here is your client's full portfolio right now:\n\n{facts}\n"
        f"{strategy_block}\n"
        f"{standing}"
        f"{_prior_advice_block(key)}\n"
        f"{capital_block}\n"
        f"You are the client's WATCHDOG advisor, not a salesman. A refreshed "
        f"brief does NOT owe the client new trades TODAY: if the book is "
        f"positioned correctly, your call is patience on existing positions. But "
        f"patience is NOT silence on growth — you are a GROWTH advisor tied to "
        f"the strategy, so you must ALWAYS scout NOT-owned names that fit the "
        f"plan and would compound the book toward the goal (the candidate list is "
        f"a start; also use your own knowledge of strategy-fit leaders, e.g. "
        f"large-cap AI names the client doesn't hold). Never "
        f"manufacture a trade to fill the list. When you DO recommend, prefix "
        f"each action with its horizon: 'Quick trade:' (days-weeks, momentum "
        f"or level-driven) or 'Long game:' (months+, compounding/position "
        f"building), so the client knows which clock it runs on.\n\n"
        f"Give your professional whole-portfolio review: overall posture, "
        f"concentration/risk assessment, and what — if anything — to do "
        f"this week (name specific tickers and levels). "
        f"{_NEWS_TRIM_RULE}"
        f'Respond with ONLY a JSON object, no markdown, with these keys: '
        f'"summary" (ONE short plain sentence — the single most important thing right now), '
        f'"posture" (string: "act" if this week genuinely calls for trades, '
        f'"watch" if the right move is patience), '
        f'"insights" (array of EXACTLY 2-3 SHORT plain-English facts about the '
        f'book — e.g. "You are 60% in AI chips." "Cash is thin at 15%." No '
        f'jargon, no filler), '
        f'"actions" (array of 1-4 strings: each a plain ORDER a beginner can '
        f'follow — verb + $amount + TICKER + "at $price" + optional "stop '
        f'$price", under 14 words, NO rationale. Examples: "Buy $150 MU at '
        f'$960; stop $905." "Trim $200 AMD if it hits $540." In a quiet week '
        f'this may be one "Hold — do nothing" line), '
        f'"risks" (array of EXACTLY 1-2 strings: the single biggest risk in '
        f'plain words + the price that would confirm it), '
        f'"scout" (array of 2-4 strings — YOUR proactive high-conviction IDEAS, '
        f'this is the client\'s #1 ask: they want YOU to find the stocks, not '
        f'pick for themselves. REQUIRED every brief. Rank by YOUR conviction, '
        f'strongest first, and LEAD each with a tag in caps: "HIGH CONVICTION" '
        f'(a quality compounder you would stake real size on) or "SPECULATIVE '
        f'UPSIDE" (an asymmetric diamond-in-the-rough that could multiply — the '
        f'client explicitly WANTS these bold calls, sized tiny). Each: the tag, '
        f'TICKER, a punchy one-line WHY YOU BELIEVE (the edge/catalyst, not '
        f'generic), the buy trigger/level, the size, and the upside target. '
        f'Champion them — say what you would DO, not just "watch". Draw from the '
        f'candidates, the whole market, and your own research; at least one HIGH '
        f'CONVICTION idea every time, and include a SPECULATIVE UPSIDE pick when '
        f'you genuinely see one. Not-owned names only), '
        f'"stances" (array of {{"symbol","call","thesis"}} — your DEFINITIVE '
        f'one-word call on EACH holding: BUY|ADD|HOLD|TRIM|SELL|WATCH, thesis '
        f'under 10 words. This becomes the single call shown on every screen, so '
        f'it MUST agree with your actions above; if you list any standing call, '
        f'keep it unless you are deliberately changing it). '
        f'Every bullet must be a single self-contained sentence under 30 words. '
        f'No lead-in phrases, no numbering — the UI renders them as a list. '
        f'CRITICAL: if a list of actions the client has already taken is '
        f'provided, open your summary by acknowledging that progress, never '
        f're-recommend a completed action, quantify progress toward any prior '
        f'target (e.g. "miner exposure was 41%, now X% — target <25%"), and '
        f'frame recommendations strictly as the next incremental step. If the '
        f'client has been de-risking, tell them when they have done ENOUGH '
        f'rather than defaulting to more cuts.'
    )
    raw, sid = _run_claude(prompt, research=deep)
    note = _parse_note("PORTFOLIO", "claude", raw) if raw else \
        _fallback_note("PORTFOLIO", facts, all_signals)
    if raw and sid:
        _remember_session(key, sid)
    # The brief's per-holding calls become the standing calls, so the single-
    # stock reviews and slaps agree with what the brief just said.
    if raw:
        try:
            price_by = {r.symbol: getattr(r.quote, "price", None) for r in reports}
            s, e = raw.find("{"), raw.rfind("}")
            obj = json.loads(raw[s : e + 1]) if s != -1 and e > s else {}
            for st in (obj.get("stances") or []):
                sym = str(st.get("symbol") or "").upper()
                if sym:
                    stance_service.set_stance(
                        sym, st.get("call"), headline=str(st.get("thesis") or ""),
                        thesis=str(st.get("thesis") or ""), source="brief",
                        price=price_by.get(sym))
        except Exception:
            pass
    _remember_history(key, note)
    _cache[key] = (time.time(), note)
    return note


def advise_stay_course(read: dict, summary, reports, risk) -> dict:
    """Narrate the Stay-the-Course read in the advisor's warm long-game voice.

    `read` is the deterministic staycourse.read() output (posture + grounded
    facts). One standard-tier Claude call phrases the reassurance; if Claude is
    unavailable the deterministic reasons stand as-is. Cached by posture so a
    flip between hold/act regenerates immediately. This NEVER suppresses an
    alert — it only frames the quiet, when impatience does its damage."""
    posture = read.get("posture", "hold")
    key = f"portfolio:staycourse:{posture}"
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
        return hit[1]

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    base = {"posture": posture, "headline": read["headline"],
            "reasons": read["reasons"], "closer": read["closer"],
            "metrics": read.get("metrics", {}), "generated_at": stamp}

    if not settings.ADVISOR_ENABLED:
        return {**base, "engine": "deterministic"}

    facts = _facts_from_portfolio(summary, reports, risk, [])
    m = read.get("metrics", {})
    if posture == "hold":
        task = (
            "This is a QUIET week: nothing in the client's plan needs action and "
            "no warning has fired. Your job is to give the client EARNED "
            "permission to hold — warm, confident reassurance grounded ONLY in "
            "the facts above (holdings still trending up, progress to the goal, a "
            "position they held from its low back up, gains already booked). "
            "Reframe holding as the active, disciplined, winning move — never a "
            "shrug. Remind them a quiet week is the plan working and their "
            "patience through past drawdowns is what pays them. Do NOT invent a "
            "trade or manufacture urgency. Do NOT use jargon.")
    else:
        flagged = m.get("flagged") or []
        moves = m.get("ready_moves") or []
        specifics = ""
        if flagged:
            specifics += ("\nThe ONLY alert(s) that fired (name the RIGHT ones, "
                          "do NOT invent or guess a different ticker): "
                          + "; ".join(flagged) + ".")
        if moves:
            specifics += ("\nThe plan move(s) ready to act on: "
                          + "; ".join(moves) + ".")
        task = (
            f"This week the client has {m.get('ready_count', 0)} ready move(s) in "
            f"their plan and {m.get('critical_count', 0)} alert(s).{specifics} "
            "Briefly point them to the plan/alert for those, then reassure them "
            "the REST of the book stays put and compounds. Confident and calm, "
            "not alarmed. Cite ONLY the tickers named above for what needs "
            "action — never guess which name has an alert. No jargon.")

    prompt = (
        f"{_PERSONA}\n\n"
        f"Here is your client's full portfolio right now:\n\n{facts}\n\n"
        f"{task}\n\n"
        f'Respond with ONLY a JSON object, no markdown, with keys: '
        f'"headline" (ONE short warm sentence — the reassurance in plain words), '
        f'"reasons" (array of 3-5 short plain-English bullets, each a SPECIFIC '
        f'fact from the data that justifies staying the course — cite the real '
        f'numbers, no jargon, under 24 words each), '
        f'"closer" (ONE encouraging plain sentence about the long game). '
        f'Warm and human, never a lecture, never empty "stay calm" filler.'
        f"{_PLAIN_STYLE}"
    )
    raw, _ = _run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    out = {**base, "engine": "claude"}
    if raw:
        try:
            s, e = raw.find("{"), raw.rfind("}")
            obj = json.loads(raw[s : e + 1]) if s != -1 and e > s else {}
            headline = str(obj.get("headline") or "").strip()
            reasons = _as_bullets(obj.get("reasons"))
            closer = str(obj.get("closer") or "").strip()
            if headline:
                out["headline"] = headline
            if reasons:
                out["reasons"] = reasons
            if closer:
                out["closer"] = closer
        except (ValueError, TypeError):
            out = {**base, "engine": "deterministic"}
    else:
        out = {**base, "engine": "deterministic"}

    _cache[key] = (time.time(), out)
    return out


def advise_breakout(cand: BreakoutCandidate, force: bool = False,
                    deep: bool = False) -> AdvisorNote:
    key = f"breakout:{cand.symbol}"
    if not force and not deep:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
            return hit[1]

    i = cand.indicators
    facts = (
        f"Symbol: {cand.symbol} | Theme: {cand.theme} | Price ${cand.price}\n"
        f"Breakout readiness score: {cand.score}/100\n"
        f"RSI {i.rsi} | MACD {i.macd}/{i.macd_signal} | Trend {i.trend}\n"
        f"% from 52w high {i.pct_from_52w_high} | Volume {i.volume_ratio}x avg\n"
        f"Bullish signals: " + "; ".join(s.detail for s in cand.signals)
    )
    if not settings.ADVISOR_ENABLED:
        note = _fallback_note(cand.symbol, facts, cand.signals)
        _cache[key] = (time.time(), note)
        return note

    from . import stance as stance_service
    stable = stance_service.is_stable(cand.symbol, cand.price)
    prior_stance = stance_service.get(cand.symbol)
    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"A breakout screen flagged {cand.symbol} — a LEAD, not an order:\n\n"
        f"{facts}\n"
        f"{_book_context()}"
        f"{stance_service.block(cand.symbol, cand.price)}"
        f"{_prior_advice_block(key, cand.symbol)}"
        f"\nGive your DEFINITIVE read — do NOT force a bull case. Agree only if "
        f"you would genuinely act now; if it is extended, unconfirmed, or against "
        f"your standing call, say HOLD or AVOID. If constructive, give the entry "
        f"zone, the level that confirms the breakout, a stop, and a size vs the "
        f"book. {_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(
        prompt, research=deep,
        model=None if deep else settings.CLAUDE_MODEL_STANDARD)
    note = _parse_note(cand.symbol, "claude", raw) if raw else \
        _fallback_note(cand.symbol, facts, cand.signals)
    if raw and sid:
        _remember_session(key, sid)
    # Consistency: hold the standing call if nothing material moved; otherwise
    # this becomes the standing call so the radar can't contradict the book.
    if stable and prior_stance:
        note.call = prior_stance["action"]
    elif note.call:
        try:
            stance_service.set_stance(
                cand.symbol, note.call, headline=note.summary, thesis=note.summary,
                source="breakout", price=cand.price)
        except Exception:
            pass
    _remember_history(key, note)
    _cache[key] = (time.time(), note)
    return note


# ------------------------------------------------------------------ follow-up
_ASK_FMT = (
    "You CANNOT change the client's holdings, journal or records from this chat. "
    "If the client corrects a fact about a TRADE they made (e.g. 'we never made "
    "that trade'), accept it for THIS answer and point them to the Action Journal "
    "to fix it — NEVER claim you 'updated your memory' or 'logged it'. But for "
    "questions about IDEAS, not-owned names, or which pick is better (e.g. 'why "
    "PANW not VRT?'), just ANSWER with your reasoning and give the decisive call — "
    "do NOT deflect to fixing a journal; there is nothing there to fix. If you "
    "previously called one name the better buy, recommend THAT one, or explain "
    "what changed. "
    'Respond with ONLY a JSON object, no markdown: '
    '{"answer": string — LEAD WITH THE CONCRETE CALL in plain words, one line: '
    'a buy ("Buy $200 NVDA near $185"), a sell/trim ("Trim $150 AMD if it hits '
    '$540"), a hold ("Hold — do nothing"), or a watch ("Watch $180; add there"). '
    'Be decisive, take a side, no hedging, '
    '"points": array of 0-4 bullets — the specifics (size, entry, stop, target) '
    'and the ONE reason, each a plain sentence under 22 words, no jargon}. '
    'No lead-in phrases.'
)


def _live_snapshot(kind: str, symbol: str | None) -> tuple[str, list[dict]]:
    """A fresh live-price block to prepend to every follow-up. A resumed
    Claude session still holds the prices from when the brief was built —
    possibly hours old. This re-states the current tick and orders the model
    to use it, so the agent can never answer off a stale in-context number.
    Returns (prompt_block, [price receipts for the UI])."""
    from . import portfolio as pf_service
    reports = []
    try:
        if kind in ("portfolio", "strategy"):
            _, held = pf_service.portfolio_summary()
            reports = held[:12]
        elif symbol:
            reports = [pf_service.build_report(symbol.upper())]
    except Exception:
        reports = []
    lines, receipts = [], []
    for r in reports:
        q = getattr(r, "quote", None)
        if not q:
            continue
        tag = "" if q.source == "live" else f" [{q.source} data]"
        lines.append(f"{r.symbol} ${q.price} ({q.change_pct:+.2f}% today){tag}")
        receipts.append({"symbol": r.symbol, "price": q.price,
                         "change_pct": q.change_pct, "data_source": q.source})
    if not lines:
        return "", []
    block = ("CURRENT LIVE PRICES (pulled " + time.strftime("%H:%M:%S")
             + " ET) — use THESE exact numbers; they OVERRIDE any prices from "
             "earlier in our conversation:\n" + "\n".join(lines) + "\n\n")
    return block, receipts


def _parse_dollar(text: str):
    import re
    best = 0.0
    for m in re.finditer(r"\$\s*([\d,]+(?:\.\d+)?)", text or ""):
        try:
            best = max(best, float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return best or None


_OPT_NOTE = (
    "OPTIONS RULES: recommend ONLY defined-risk LONG options — buy a call "
    "(bullish) or a put (bearish). The MAX LOSS is the premium paid, period; "
    "never suggest selling naked options, spreads the client didn't ask for, or "
    "anything with undefined risk. This is a leveraged, high-conviction bet on a "
    "name and thesis you already believe in — size it SMALL (options can expire "
    "worthless: treat the whole premium as money you can lose). Match the "
    "expiration to how long the thesis needs to play out, and be honest that the "
    "trade goes to ZERO if the move doesn't happen by expiry."
)


def advise_option(symbol: str, trade: dict, side: str, target: float | None,
                  force: bool = False) -> dict:
    """Frame a suggested defined-risk options trade as a conviction play:
    thesis, why this contract, sizing, and the honest downside."""
    sym = symbol.upper()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    key = f"option:{sym}:{side}"
    if not force:
        hit = _reco_cache.get(key)
        if hit and (time.time() - hit[0]) < _RECO_TTL:
            return hit[1]

    def _fallback() -> dict:
        return {"engine": "fallback", "generated_at": stamp,
                "thesis": f"A {side} on {sym} caps your risk at the ${trade.get('cost_per_contract', 0):,} premium.",
                "contract": "", "sizing": "Size it small — you can lose the whole premium.",
                "risk": "If the move doesn't happen by expiry, the option expires worthless (total loss of premium)."}

    if not settings.ADVISOR_ENABLED or not trade:
        out = _fallback()
        _reco_cache[key] = (time.time(), out)
        return out

    report = None
    try:
        report = pf_service.build_report(sym)
        facts = _facts_from_report(report)
    except Exception:
        facts = f"Symbol {sym}."
    from . import stance as stance_service
    _spot = report.quote.price if report else None
    tdesc = (
        f"SUGGESTED DEFINED-RISK TRADE (already screened for liquidity): BUY the "
        f"{trade['symbol']} {trade['expiration']} ${trade['strike']:g} {side} at "
        f"~${trade['premium']:g} (delta {trade['delta']}, {trade['dte']} days out, "
        f"IV {trade['iv_pct']}%). Cost = MAX RISK ${trade['cost_per_contract']:,} "
        f"per contract. Breakeven ${trade['breakeven']:g}."
    )
    if trade.get("value_at_target"):
        tdesc += (f" If {sym} reaches ${target:g} by expiry the contract is worth "
                  f"~${trade['value_at_target']:,} (~{trade['return_at_target_x']}x the premium).")

    prompt = (
        f"{_PERSONA}\n\n{_OPT_NOTE}\n\nThe client wants a high-conviction, "
        f"defined-risk OPTIONS play on {sym}.\n\n{facts}\n{_book_context()}"
        f"{stance_service.block(sym, _spot)}\n"
        f"{tdesc}\n\n"
        f"Assess whether this is a trade you'd back for the client and frame it. "
        f'Respond with ONLY a JSON object: {{"thesis": string — one plain sentence '
        f'on why {sym} and why now (the directional bet), "contract": string — one '
        f'sentence on why THIS strike/expiry fits the thesis and timeframe, '
        f'"sizing": string — how many contracts or how much to risk given the book '
        f'(remember premium is the max loss; keep it small), "risk": string — the '
        f"honest downside in plain words}}. Under 22 words each, no jargon. {_PLAIN_STYLE}"
    )
    raw, _ = _run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    out = _fallback()
    if raw:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e > s:
            try:
                obj = json.loads(raw[s:e + 1])
                out = {
                    "engine": "claude", "generated_at": stamp,
                    "thesis": str(obj.get("thesis") or out["thesis"]),
                    "contract": str(obj.get("contract") or ""),
                    "sizing": str(obj.get("sizing") or out["sizing"]),
                    "risk": str(obj.get("risk") or out["risk"]),
                }
            except json.JSONDecodeError:
                pass
    _reco_cache[key] = (time.time(), out)
    return out


def _pending_commitments() -> str:
    """Open pins + armed tripwires with their dollar amounts. These COMPETE for
    the same cash — feeding them in is what stops the advisor recommending a set
    of buys that TOGETHER breach the floor even though each looks fine alone."""
    from . import pins as pins_svc, watchpoints as wp_svc
    rows, total_buy = [], 0.0
    _buyish = ("buy", "add", "rotate", "into", "start")

    def _tkr(txt: str, sym) -> str | None:
        if sym:
            return str(sym).upper()
        m = re.search(r"\b([A-Z]{2,5})\b", txt or "")
        return m.group(1) if m else None

    # Collapse duplicate same-ticker/same-side commitments so the advisor doesn't
    # report "duplicate NVDA buys" when the dashboard (which dedupes) shows one.
    seen: set = set()
    try:
        for p in pins_svc.list_pins():  # open first, newest first
            if p.get("status") != "open":
                continue
            txt = p.get("text", "")
            is_buy = any(w in txt.lower() for w in _buyish)
            tkr = _tkr(txt, p.get("symbol"))
            key = (tkr, is_buy)
            if tkr and key in seen:
                continue
            if tkr:
                seen.add(key)
            amt = _parse_dollar(txt)
            rows.append(f"PIN [{tkr or '-'}]: {txt}"
                        + (f" (~${amt:,.0f})" if amt else ""))
            if amt and is_buy:
                total_buy += amt
    except Exception:
        pass
    try:
        for w in wp_svc.list_watchpoints(include_triggered=False):
            note = w.get("note", "")
            is_buy = w.get("side") == "buy" or any(x in note.lower() for x in _buyish)
            key = (str(w["symbol"]).upper(), is_buy)
            if key in seen:
                continue
            seen.add(key)
            amt = _parse_dollar(note)
            rows.append(f"TRIPWIRE [{w['symbol']} {wp_svc.condition_str(w)}]: {note}"
                        + (f" (~${amt:,.0f})" if amt else ""))
            if amt and is_buy:
                total_buy += amt
    except Exception:
        pass
    if not rows:
        return ""
    head = ("QUEUED ACTIONS you have already pinned/armed (they draw on the SAME "
            "cash — these buys compete with each other")
    if total_buy:
        head += f"; pending BUY commitments total ~${total_buy:,.0f}"
    return head + "):\n" + "\n".join("  - " + r for r in rows)


def _book_context(summary=None, reports=None) -> str:
    """The client's WHOLE portfolio in one block — cash, holdings, allocation —
    so a single-stock chat/review can still reason about cash impact and
    allocation. The advisor HAS this; it must never ask the client for it."""
    from . import portfolio as pf_service
    if summary is None:
        try:
            summary, reports = pf_service.portfolio_summary()
        except Exception:
            return ""
    if not summary:
        return ""
    tv = summary.total_market_value or 0
    # Cash and SGOV are the SAME thing — equivalent deployable dry powder. The
    # "Cash & Income" bucket already sums raw cash + SGOV, so use it as ONE pool.
    dry = summary.by_theme.get("Cash & Income", summary.cash) if summary.by_theme else summary.cash
    dry_pct = (dry / tv * 100) if tv else 0
    sgov = max(dry - summary.cash, 0)
    lines = [
        "CLIENT'S FULL PORTFOLIO (you already HAVE this — never ask them for "
        "cash or holdings):",
        f"Total book ${tv:,.0f}. DRY POWDER = ${dry:,.0f} ({dry_pct:.0f}% of "
        f"book) — this is cash + SGOV treated as ONE deployable pool (they are "
        f"EQUIVALENT; do not treat SGOV as untouchable vs cash). Of it, "
        f"${summary.cash:,.0f} is idle cash and ${sgov:,.0f} is SGOV that can be "
        f"sold to fund a buy. Any cash/SGOV floor applies to this COMBINED dry "
        f"powder, not to cash alone.",
    ]
    held = sorted((r for r in (reports or []) if r.market_value),
                  key=lambda r: r.market_value or 0, reverse=True)
    if held:
        lines.append("Holdings: " + ", ".join(
            f"{r.symbol} ${r.market_value:,.0f} ({(r.market_value / tv * 100):.0f}%)"
            for r in held[:14]))
    # Core convictions the owner has designated — protect them.
    try:
        core = [s.upper() for s in pf_service.load_portfolio().get("core_convictions", [])]
        if core:
            lines.append(
                "CLIENT'S CORE CONVICTIONS (long-term holds): " + ", ".join(core)
                + ". On weakness the play is ACCUMULATE, not sell. NEVER "
                "recommend selling these at a loss on a technical break or price "
                "drop — only flag for re-examination if the BUSINESS thesis "
                "actually breaks, and even then present the case, don't order a cut.")
    except Exception:
        pass
    if summary.by_theme:
        lines.append("By theme: " + ", ".join(
            f"{k} ${v:,.0f}" for k, v in
            sorted(summary.by_theme.items(), key=lambda x: -x[1])[:6]))
    # The hard guardrails the advisor keeps citing MUST be in context — and so
    # must anything already queued that would breach them.
    try:
        from . import strategy as _strat
        doc = _strat.load()
        if doc and doc.get("approved") and doc.get("guardrails"):
            lines.append("HARD GUARDRAILS (do not violate): "
                         + " | ".join(doc["guardrails"]))
    except Exception:
        pass
    pend = _pending_commitments()
    if pend:
        lines.append(pend)
    lines.append(
        "CRITICAL: account for the QUEUED actions above — they draw on the SAME "
        "cash/SGOV. NEVER recommend or endorse buys that TOGETHER with what is "
        "already pinned/armed breach a guardrail (esp. the SGOV/cash floor). If "
        "the queued plan already cannot all be funded within the floor, SAY SO "
        "and PRIORITIZE: which fires first, which to cut or resize. Do not cite a "
        "floor while blessing trades that break it — reconcile into ONE coherent, "
        "funded plan.")
    return "\n".join(lines) + "\n\n"


def ask(kind: str, symbol: str | None, question: str, deep: bool = False) -> dict:
    """Answer a follow-up question about a prior advisor note.

    Resumes the claude session that produced the note, so the model still has
    the full brief and data in context. If no session exists (fresh boot,
    fallback note), the current facts are rebuilt and sent with the question.
    deep=True lets the answer pull live news/sentiment via web search.
    """
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if not settings.ADVISOR_ENABLED:
        return {"engine": "fallback", "generated_at": stamp, "points": [],
                "answer": "The AI advisor is disabled (ADVISOR_ENABLED=0), so "
                          "follow-up questions can't be answered right now."}

    # If the client is asking about news/a catalyst, always go check the web —
    # they shouldn't have to toggle "deep research" to get a current answer.
    if not deep and re.search(
            r"\b(news|announce\w*|headline|catalyst|deal|partner\w*|acqui\w*|"
            r"merger|report(ed|s)?|rumou?r|upgrade|downgrade|guidance)\b",
            question, re.I):
        deep = True

    if kind == "portfolio":
        key = "portfolio:brief"
    elif kind == "strategy":
        key = "strategy:plan"
    else:
        key = f"{kind}:{symbol}"
    research_note = _RESEARCH_PREFIX if deep else ""
    snapshot, price_receipts = _live_snapshot(kind, symbol)
    # Carry the standing call(s) so a follow-up can't contradict the last verdict.
    from . import stance as stance_service
    if kind in ("portfolio", "strategy"):
        try:
            from . import portfolio as _pf
            _, _held = _pf.portfolio_summary()
            standing = stance_service.book_block([r.symbol for r in _held])
        except Exception:
            standing = ""
    else:
        standing = stance_service.block(symbol or "")
    # EVERY chat turn — resume or cold, stock or portfolio — carries the whole
    # book (cash, holdings, weights). The resume path used to send only prices +
    # standing calls, so a resumed portfolio chat asked for cash it already had.
    snapshot = snapshot + standing + _book_context()
    raw = sid = None
    prior = _sessions.get(key)
    ask_model = None if deep else settings.CLAUDE_MODEL_STANDARD
    if prior:
        # A resumed thread can drift from its own earlier answers. Anchor every
        # turn to the authoritative current state and forbid contradicting it —
        # if an earlier answer in this chat conflicts, THIS wins.
        anchor = (
            "AUTHORITATIVE CURRENT STATE — this OVERRIDES anything said earlier "
            "in this conversation. If a prior answer here conflicts with the "
            "standing call or prices below, that earlier answer was wrong; align "
            "to THIS and, if it changes your prior reply, say so in one line.\n\n"
            f"{snapshot}")
        raw, sid = _run_claude(
            f"{research_note}{anchor}Client follow-up question: {question}\n\n{_ASK_FMT}",
            resume=prior, research=deep, model=ask_model)

    if raw is None:
        # No live session — rebuild context and ask cold.
        from . import insights as insights_service
        from . import portfolio as pf_service
        if kind in ("portfolio", "strategy"):
            summary, reports = pf_service.portfolio_summary()
            facts = _facts_from_portfolio(
                summary, reports,
                insights_service.compute_risk(reports),
                insights_service.build_alerts(reports))
            if kind == "strategy":
                from . import strategy as strategy_service
                block = strategy_service.facts_block()
                doc = strategy_service.load()
                if not block and doc:  # draft exists but isn't approved yet
                    block = ("DRAFT strategy under discussion:\n"
                             f"Thesis: {doc.get('thesis')}\n"
                             "Short-term: " + "; ".join(doc.get("short_term", [])[:5]))
                facts = f"{facts}\n\n{block}" if block else facts
        else:
            facts = _facts_from_report(pf_service.build_report(symbol))
        prior_note = _prior_advice_block(key, symbol)
        prompt = (f"{_PERSONA}\n\n{research_note}{snapshot}"
                  f"The client's current data:\n\n{facts}\n{prior_note}"
                  f"\nClient question: {question}\n\n{_ASK_FMT}")
        raw, sid = _run_claude(prompt, research=deep, model=ask_model)

    if raw is None:
        return {"engine": "fallback", "generated_at": stamp, "points": [],
                "answer": "The advisor is unavailable right now (Claude CLI "
                          "did not respond). Try again in a moment."}

    if sid:
        _remember_session(key, sid)
    answer, points = raw.strip(), []
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            answer = str(obj.get("answer", "") or "").strip() or raw.strip()
            points = _as_bullets(obj.get("points"))
        except json.JSONDecodeError:
            pass
    return {"engine": "claude", "generated_at": stamp,
            "answer": answer, "points": points, "prices": price_receipts,
            "as_of": stamp}


# ------------------------------------------------- unified recommendation
# Every notification — signal, runner ignition, or attention alert — gets an
# advisor recommendation that looks at the client's actual portfolio. The
# answer may be "Hold, no action", but the ANALYSIS is always done: raw data
# ("IREN -5%") without a recommended action leads to bad decisions.
_reco_cache: dict[str, tuple[float, dict]] = {}
_RECO_TTL = 3600

_RECO_FMT = (
    'Respond with ONLY a JSON object, no markdown: '
    '{"action": one word — BUY | ADD | TRIM | SELL | HOLD | AVOID, '
    '"headline": punchy under-10-word verdict, '
    '"what": ONE sentence — the exact move in plain terms (or "Hold — no action" '
    'with the reason); under 22 words, '
    '"entry": the exact price or tight zone to act at now (e.g. "$375-378" or '
    '"market ~$376"); empty string ONLY if action is HOLD/no-action, '
    '"size": how much, CONCRETELY — a dollar amount and rough % of book, sized to '
    'risk (e.g. "$150, ~1.4% of book; ~0.3% book risk to the stop"). A low-float '
    'runner is a lottery ticket: size it tiny but STATE THE NUMBER. Empty only if '
    'no action, '
    '"target": the concrete profit target price (e.g. "$410 (+9%)") or "", '
    '"stop": the concrete invalidation price (e.g. "daily close below $362") or "", '
    '"why": array of 2-3 bullet strings citing the numbers and the position}. '
    "Be DECISIVE — NEVER say 'consider', 'you could', or 'think about'. If you "
    "recommend action, give the exact entry, dollar size, stop AND target — no "
    "dancing. If HOLD, name the single trigger that would change it. Ground "
    "every number in the data given; never invent figures you cannot support."
)


def recommend(symbol: str, event: str, kind: str = "alert",
              force: bool = False) -> dict:
    """Portfolio-aware recommendation for a notification event.

    kind: 'alert' | 'signal' | 'runner'. Cached 1h per (symbol, event)."""
    key = f"reco:{kind}:{symbol}:{event}"[:200]
    # A trading advisor can't serve hour-old calls while the market moves.
    # Tight TTL during market hours; the full hour only when the tape is shut.
    from .market_data import _market_hours
    ttl = 120 if _market_hours() else _RECO_TTL
    if not force:
        hit = _reco_cache.get(key)
        if hit and (time.time() - hit[0]) < ttl:
            return hit[1]

    from . import insights as insights_service
    from . import portfolio as pf_service
    from . import strategy as strategy_service

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        summary, held = pf_service.portfolio_summary()
    except Exception:
        summary, held = None, []
    report = None
    for r in held:
        if r.symbol == symbol.upper():
            report = r
            break
    if report is None:
        try:
            report = pf_service.build_report(symbol.upper())
        except Exception:
            report = None

    # Freshness receipt — the exact price/time this call reasoned from, so the
    # UI can show "as of HH:MM ET · $X · live" and stale data is never silent.
    q = getattr(report, "quote", None)
    fresh = {
        "price": getattr(q, "price", None),
        "change_pct": getattr(q, "change_pct", None),
        "data_source": getattr(q, "source", None),
        "as_of": stamp,
    } if q else {"as_of": stamp}

    # Fallback (no Claude): a safe, generic-but-honest read.
    def _fallback() -> dict:
        held_note = (f"You hold {report.shares:g} shares, P/L "
                     f"{report.unrealized_pl_pct:+.1f}%. " if report and report.shares else "")
        return {
            "engine": "fallback", "generated_at": stamp, "action": "HOLD",
            "headline": f"{symbol}: review before acting",
            "what": f"{held_note}No automated call — open {symbol} and size any "
                    f"move to your plan.",
            "why": [event, "Advisor unavailable — deterministic fallback."],
            "entry": "", "size": "", "target": "", "stop": "", **fresh,
        }

    if not settings.ADVISOR_ENABLED:
        _reco_cache[key] = (time.time(), _fallback())
        return _reco_cache[key][1]

    from . import stance as stance_service
    facts = _facts_from_report(report) if report else f"Symbol {symbol} (not held)."
    if summary:
        bv = summary.total_market_value
        book = (
            f"CLIENT'S ACTUAL BOOK: ${bv:,.0f} total (the WHOLE portfolio — never "
            f"assume a generic $100k), cash "
            f"${summary.by_theme.get('Cash & Income', 0):,.0f}. Fractional shares "
            f"are available: size in DOLLARS (any amount), fractional share count "
            f"is fine, never round to whole shares. SIZE TO CONVICTION AND RISK — "
            f"do not default to a timid cap: a tentative or extended/chase setup "
            f"gets a small starter (a few % of book), but a HIGH-conviction, "
            f"thesis-backed setup can justify a meaningful position (10-20%+). "
            f"Recommend the size you genuinely believe is CORRECT and say why. "
            f"Anchor size to the stop (wider stop = smaller size) so a stop-out is "
            f"a loss the book can absorb; don't over-concentrate the whole book in "
            f"one name; never exceed the cash/book available.")
    else:
        book = ""
    # Full portfolio context — cash pool, holdings, guardrails, queued actions,
    # AND the client's CORE CONVICTIONS (so a core name is never told to sell at
    # a loss on a technical break).
    book = book + "\n\n" + _book_context()
    strat = strategy_service.facts_block()
    _px = fresh.get("price")
    _stable = stance_service.is_stable(symbol.upper(), _px)
    _prior_stance = stance_service.get(symbol.upper())
    standing = stance_service.block(symbol.upper(), _px)
    prior = _prior_advice_block(f"stock:{symbol.upper()}", symbol.upper())

    # A big recent move usually means a catalyst — verify it live (web) so a
    # trim/add is never recommended blind to the news that's driving it.
    _chg = fresh.get("change_pct")
    big_move = _chg is not None and abs(_chg) >= 6
    prompt = (
        f"{_RESEARCH_PREFIX if big_move else ''}"
        f"{_PERSONA}\n\nA watchdog notification just fired for the client:\n"
        f"EVENT: {symbol} — {event}\n\n{facts}\n{book}\n{strat}\n{standing}{prior}\n"
        f"As their advisor, say clearly what they should DO about THIS event, "
        f"considering their position, cash and plan. The answer may be 'Hold — "
        f"no action' (e.g. normal volatility, thesis intact) — but justify it "
        f"and give the level that WOULD change it. If action is warranted, give "
        f"the exact move, size (<=1.5% risk of book) and stop. {_NEWS_TRIM_RULE}{_RECO_FMT}"
    )
    raw, _ = _run_claude(
        prompt, research=big_move,
        model=None if big_move else settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        _reco_cache[key] = (time.time(), _fallback())
        return _reco_cache[key][1]

    out = _fallback()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        try:
            obj = json.loads(raw[s : e + 1])
            action = str(obj.get("action") or "HOLD").strip().upper().split()[0]
            out = {
                "engine": "claude", "generated_at": stamp,
                "action": action if action in
                          {"BUY", "ADD", "TRIM", "SELL", "HOLD", "AVOID"} else "HOLD",
                "headline": str(obj.get("headline") or f"{symbol}: {event}"),
                "what": str(obj.get("what") or out["what"]),
                "why": _as_bullets(obj.get("why")) or [event],
                "entry": str(obj.get("entry") or ""),
                "size": str(obj.get("size") or ""),
                "target": str(obj.get("target") or ""),
                "stop": str(obj.get("stop") or ""),
                **fresh,
            }
            # Hold the call if nothing material moved; otherwise this fresh
            # call becomes the standing one.
            if _stable and _prior_stance:
                out["action"] = _prior_stance["action"]
            else:
                try:
                    stance_service.set_stance(
                        symbol.upper(), out["action"], headline=out["headline"],
                        thesis=out["what"], target=out["target"], stop=out["stop"],
                        source=f"reco:{kind}", price=fresh.get("price"))
                except Exception:
                    pass
        except json.JSONDecodeError:
            pass
    _reco_cache[key] = (time.time(), out)
    return out


def reevaluate_plan(pin: dict, baseline: float, current: float,
                    move: float) -> dict:
    """Plan Watch: does a STAGED (not-yet-executed) plan still hold after the
    market moved? Returns {plan_status: holds|changed, action, headline, what,
    why[], target, stop} + freshness. The advisor decides — a loss-control SELL
    becomes wrong if the name is now running (ride it), a dip-buy becomes wrong
    if price gapped away."""
    from . import portfolio as pf_service
    from . import stance as stance_service
    sym = (pin.get("symbol") or "").upper()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def _fallback() -> dict:
        return {"engine": "fallback", "generated_at": stamp,
                "plan_status": "holds", "action": "HOLD",
                "headline": f"{sym}: re-check your staged plan",
                "what": f"{sym} moved {move:+.1%} since you staged this — open it "
                        f"and confirm the plan still fits.",
                "why": [pin.get("text", "")], "target": "", "stop": "",
                "as_of": stamp}

    if not settings.ADVISOR_ENABLED or not sym:
        return _fallback()

    try:
        report = pf_service.build_report(sym)
        facts = _facts_from_report(report)
        price = getattr(report.quote, "price", current)
        src = getattr(report.quote, "source", None)
    except Exception:
        facts, price, src = f"Symbol {sym}.", current, None

    prompt = (
        f"{_PERSONA}\n\n"
        f"The client STAGED this plan earlier and has NOT executed it yet:\n"
        f'STAGED PLAN: "{pin.get("text", "")}"\n'
        f"When staged, {sym} was about ${baseline:.2f}. It is now ${price:.2f} "
        f"({move:+.1%} since).\n\n{facts}\n{_book_context()}{stance_service.block(sym)}\n"
        f"Decide whether this staged plan STILL HOLDS or has MATERIALLY CHANGED "
        f"given the move and current data. Be decisive and protect the client: a "
        f"stop-loss / loss-control SELL becomes the WRONG move if the name is now "
        f"running — that may be a profit play to RIDE, not an exit; a staged "
        f"dip-buy becomes wrong if price has gapped away from the entry. "
        f'Respond with ONLY JSON: {{"plan_status": "holds" | "changed", '
        f'"action": one word BUY|ADD|TRIM|SELL|HOLD|AVOID, "headline": under-10-'
        f'word verdict, "what": ONE sentence — the revised move (or why to stick '
        f'to the plan), under 22 words, "why": array of 2-3 bullets citing the '
        f'numbers, "target": level or "", "stop": level or ""}}.'
    )
    raw, _ = _run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return _fallback()

    out = _fallback()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        try:
            obj = json.loads(raw[s : e + 1])
            status = str(obj.get("plan_status") or "holds").strip().lower()
            action = str(obj.get("action") or "HOLD").strip().upper().split()[0]
            out = {
                "engine": "claude", "generated_at": stamp,
                "plan_status": "changed" if status == "changed" else "holds",
                "action": action if action in
                          {"BUY", "ADD", "TRIM", "SELL", "HOLD", "AVOID"} else "HOLD",
                "headline": str(obj.get("headline") or f"{sym}: staged plan review"),
                "what": str(obj.get("what") or out["what"]),
                "why": _as_bullets(obj.get("why")) or [pin.get("text", "")],
                "target": str(obj.get("target") or ""),
                "stop": str(obj.get("stop") or ""),
                "price": price, "data_source": src, "as_of": stamp,
            }
            # A changed plan sets a fresh standing call on the name.
            if out["plan_status"] == "changed":
                try:
                    stance_service.set_stance(
                        sym, out["action"], headline=out["headline"],
                        thesis=out["what"], target=out["target"],
                        stop=out["stop"], source="plan-watch", price=price)
                except Exception:
                    pass
        except json.JSONDecodeError:
            pass
    return out
