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
        "line, including levels you told the client to wait for.\n"
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
    "You are a senior portfolio advisor with 25 years across Charles Schwab "
    "and a long/short equity fund: CMT charterholder, CFP, deep in the "
    "technology, AI, semiconductor, energy and data-center sectors, and a "
    "student of O'Neil, Minervini, Mark Douglas and Kahneman. The "
    "non-negotiables of your practice:\n"
    "- Capital preservation before returns: every entry has a predefined "
    "invalidation level, and risk per new position is <= 1.5% of the book "
    "(position size = risk dollars / distance to stop). State the size.\n"
    "- Cut losers mechanically at their stops; never average down a broken "
    "thesis; let winners run with trailed stops; never revenge-trade.\n"
    "- Trade WITH the regime: when the benchmark is above its 200-day, lean "
    "risk-on; below it, halve size and hold more cash.\n"
    "- Momentum entries require volume confirmation; mean-reversion entries "
    "require intact long-term structure. Chasing a name >2 ATR extended is "
    "forbidden — give the pullback level instead.\n"
    "- Respect binary events: no new entries within 2 days of earnings; flag "
    "any holding reporting within a week.\n"
    "- Low-float microcap runners (the MGRT type: <20M float, recent IPO, "
    "vertical on volume) are TRADES not investments: lottery-ticket size "
    "(<=1% of book), a predefined exit set before entry, and never chased "
    "when already extended — the same thin float that enables a 10x enables "
    "a -90% with no bid. Separate this speculation sleeve from the core.\n"
    "- Expectancy over ego: cite only numbers you were given, never invent "
    "data, and say 'insufficient data' rather than guess.\n"
    "- Be direct. Hedging language wastes the client's time."
)

_SCHEMA_HINT = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
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
        lines.append("Recent headlines:")
        for n in r.news[:6]:
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
    exe = shutil.which(settings.CLAUDE_BIN) or settings.CLAUDE_BIN
    cmd = [exe, "-p", "--output-format", "json"]
    if resume:
        cmd += ["--resume", resume]
    if research:
        cmd += ["--allowedTools", "WebSearch", "WebFetch"]
    chosen = model if model is not None else settings.CLAUDE_MODEL
    if chosen:
        cmd += ["--model", chosen]
    timeout = max(settings.ADVISOR_TIMEOUT, 300) if research \
        else settings.ADVISOR_TIMEOUT
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[advisor] claude CLI unavailable: {exc!r}")
        return None, None
    if proc.returncode != 0:
        print(f"[advisor] claude CLI rc={proc.returncode}: {proc.stderr[:300]}")
        return None, None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout.strip() or None, None
    if payload.get("is_error"):
        return None, None
    return payload.get("result"), payload.get("session_id")


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
    insights: list[str] = []
    actions: list[str] = []
    risks: list[str] = []
    text = raw.strip()
    # Extract JSON object if the model wrapped it in prose/fences.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            summary = str(obj.get("summary", "") or "")
            p = str(obj.get("posture", "") or "").strip().lower()
            posture = p if p in ("act", "watch") else None
            insights = _as_bullets(obj.get("insights") or obj.get("technical_read"))
            actions = _as_bullets(obj.get("actions") or obj.get("recommendation"))
            risks = _as_bullets(obj.get("risks"))
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
        insights=insights,
        actions=actions,
        risks=risks,
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

    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"Here is the current data for a stock a client holds or is "
        f"watching:\n\n{facts}\n"
        f"{_prior_advice_block(key, report.symbol)}"
        f"\nAs their advisor, give your professional read. "
        f"{_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(
        prompt, research=deep,
        model=None if deep else settings.CLAUDE_MODEL_STANDARD)
    note = _parse_note(report.symbol, "claude", raw) if raw else \
        _fallback_note(report.symbol, facts, report.signals)
    if raw and sid:
        _remember_session(key, sid)
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
            "Top NOT-owned candidates by breakout readiness (from the "
            "Discovery scan): " + "; ".join(
                f"{c.symbol} {c.score:.0f}/100 (${c.price}, {c.theme}, "
                f"RSI {c.indicators.rsi}, {c.indicators.trend})"
                for c in candidates[:5]))
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
    strategy_block = strategy_service.facts_block()
    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"Here is your client's full portfolio right now:\n\n{facts}\n"
        f"{strategy_block}\n"
        f"{_prior_advice_block(key)}\n"
        f"You are the client's WATCHDOG advisor, not a salesman. A refreshed "
        f"brief does NOT owe the client new trades: if the book is positioned "
        f"correctly, your call is patience — restate the standing levels being "
        f"watched and say explicitly that no action is needed. Never "
        f"manufacture a trade to fill the list. When you DO recommend, prefix "
        f"each action with its horizon: 'Quick trade:' (days-weeks, momentum "
        f"or level-driven) or 'Long game:' (months+, compounding/position "
        f"building), so the client knows which clock it runs on.\n\n"
        f"Give your professional whole-portfolio review: overall posture, "
        f"concentration/risk assessment, and what — if anything — to do "
        f"this week (name specific tickers and levels). "
        f'Respond with ONLY a JSON object, no markdown, with these keys: '
        f'"summary" (string: overall take in 1-2 sentences max), '
        f'"posture" (string: "act" if this week genuinely calls for trades, '
        f'"watch" if the right move is patience), '
        f'"insights" (array of 4-7 strings: portfolio health — one observation '
        f'per bullet on risk metrics, correlation/concentration, momentum, '
        f'citing the numbers), '
        f'"actions" (array of 1-5 strings: each a terse ORDER — prefix '
        f'"Quick trade:" or "Long game:" then at most 12 more words: verb, '
        f'ticker, dollar size, level, stop. Example: "Quick trade: Buy $150 '
        f'MU at $960; stop $905." NO rationale in actions — rationale lives '
        f'in insights. In a "watch" week the array may be one "Hold — no '
        f'action" bullet plus the levels being watched; when acting, include '
        f'your best buy or state the level that would create one), '
        f'"risks" (array of 2-4 strings: one risk per bullet, each paired with '
        f'the specific tripwire signal to watch). '
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
    _remember_history(key, note)
    _cache[key] = (time.time(), note)
    return note


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

    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"This stock is flagged as a potential breakout candidate:\n\n"
        f"{facts}\n"
        f"{_prior_advice_block(key, cand.symbol)}"
        f"\nMake the bull case for a near-term breakout AND state what would "
        f"invalidate it. Be specific about entry zone, the level that confirms the "
        f"breakout, and a stop. {_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(
        prompt, research=deep,
        model=None if deep else settings.CLAUDE_MODEL_STANDARD)
    note = _parse_note(cand.symbol, "claude", raw) if raw else \
        _fallback_note(cand.symbol, facts, cand.signals)
    if raw and sid:
        _remember_session(key, sid)
    _remember_history(key, note)
    _cache[key] = (time.time(), note)
    return note


# ------------------------------------------------------------------ follow-up
_ASK_FMT = (
    'Respond with ONLY a JSON object, no markdown: '
    '{"answer": string (the direct answer to the question in 1-2 sentences), '
    '"points": array of 0-4 supporting bullet strings, each a single '
    'self-contained sentence under 25 words}. No lead-in phrases.'
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

    if kind == "portfolio":
        key = "portfolio:brief"
    elif kind == "strategy":
        key = "strategy:plan"
    else:
        key = f"{kind}:{symbol}"
    research_note = _RESEARCH_PREFIX if deep else ""
    snapshot, price_receipts = _live_snapshot(kind, symbol)
    raw = sid = None
    prior = _sessions.get(key)
    ask_model = None if deep else settings.CLAUDE_MODEL_STANDARD
    if prior:
        raw, sid = _run_claude(
            f"{research_note}{snapshot}Client follow-up question: {question}\n\n{_ASK_FMT}",
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
    '"what": ONE sentence — the exact move (or "Hold — no action" with the '
    'reason), size and level; under 22 words, '
    '"why": array of 2-3 bullet strings citing the numbers and the position, '
    '"target": one sentence — the level/target that matters (or ""), '
    '"stop": one sentence — the invalidation/stop level (or "")}. '
    "Ground every number in the data given; never invent figures."
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
            "target": "", "stop": "", **fresh,
        }

    if not settings.ADVISOR_ENABLED:
        _reco_cache[key] = (time.time(), _fallback())
        return _reco_cache[key][1]

    facts = _facts_from_report(report) if report else f"Symbol {symbol} (not held)."
    book = f"Book ${summary.total_market_value:,.0f}, cash bucket " \
           f"${summary.by_theme.get('Cash & Income', 0):,.0f}." if summary else ""
    strat = strategy_service.facts_block()
    prior = _prior_advice_block(f"stock:{symbol.upper()}", symbol.upper())

    prompt = (
        f"{_PERSONA}\n\nA watchdog notification just fired for the client:\n"
        f"EVENT: {symbol} — {event}\n\n{facts}\n{book}\n{strat}\n{prior}\n"
        f"As their advisor, say clearly what they should DO about THIS event, "
        f"considering their position, cash and plan. The answer may be 'Hold — "
        f"no action' (e.g. normal volatility, thesis intact) — but justify it "
        f"and give the level that WOULD change it. If action is warranted, give "
        f"the exact move, size (<=1.5% risk of book) and stop. {_RECO_FMT}"
    )
    raw, _ = _run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
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
                "target": str(obj.get("target") or ""),
                "stop": str(obj.get("stop") or ""),
                **fresh,
            }
        except json.JSONDecodeError:
            pass
    _reco_cache[key] = (time.time(), out)
    return out
