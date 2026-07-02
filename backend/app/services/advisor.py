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


def _remember_session(key: str, sid: str) -> None:
    _sessions[key] = sid
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SESSIONS_FILE, "w") as f:
            json.dump(_sessions, f, indent=2)
    except OSError as exc:
        print(f"[advisor] could not persist sessions: {exc!r}")

_PERSONA = (
    "You are a senior financial advisor at Charles Schwab with 20+ years of "
    "experience in technical analysis and the technology, AI, semiconductor, "
    "energy and data-center/compute sectors. You are pragmatic, risk-aware, and "
    "you never give generic disclaimers-only answers. You cite the specific "
    "numbers you are given."
)

_SCHEMA_HINT = (
    'Respond with ONLY a JSON object, no markdown, with these keys: '
    '"summary" (string: your take in 1-2 sentences max), '
    '"insights" (array of 3-6 strings: what the indicators say — one specific '
    'observation per bullet, citing RSI/MACD/moving averages/volume numbers), '
    '"actions" (array of 2-4 strings: one concrete action per bullet — '
    'accumulate/hold/trim/avoid with the ticker and exact level to act at), '
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
    if r.signals:
        lines.append("Signals: " + "; ".join(f"{s.label} ({s.kind})" for s in r.signals))
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


def _run_claude(prompt: str, resume: str | None = None,
                research: bool = False) -> tuple[str | None, str | None]:
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
    if settings.CLAUDE_MODEL:
        cmd += ["--model", settings.CLAUDE_MODEL]
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
        f"watching:\n\n{facts}\n\nAs their advisor, give your professional read. "
        f"{_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(prompt, research=deep)
    note = _parse_note(report.symbol, "claude", raw) if raw else \
        _fallback_note(report.symbol, facts, report.signals)
    if raw and sid:
        _remember_session(key, sid)
    _cache[key] = (time.time(), note)
    return note


def _facts_from_portfolio(summary: PortfolioSummary, reports: list[StockReport],
                          risk: RiskMetrics, alerts: list[PortfolioAlert]) -> str:
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
        lines.append(
            f"  {r.symbol}: ${r.market_value:,.0f}, {r.quote.change_pct:+.1f}% today, "
            f"P/L {r.unrealized_pl_pct:+.1f}%, RSI {r.indicators.rsi}, "
            f"{r.indicators.trend}"
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
    return "\n".join(lines)


def advise_portfolio(summary: PortfolioSummary, reports: list[StockReport],
                     risk: RiskMetrics, alerts: list[PortfolioAlert],
                     force: bool = False, deep: bool = False) -> AdvisorNote:
    """One whole-book narrative: posture, risks, and concrete next actions."""
    key = "portfolio:brief"
    if not force and not deep:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
            return hit[1]

    facts = _facts_from_portfolio(summary, reports, risk, alerts)
    all_signals = [s for r in reports for s in r.signals]
    if not settings.ADVISOR_ENABLED:
        note = _fallback_note("PORTFOLIO", facts, all_signals)
        _cache[key] = (time.time(), note)
        return note

    prompt = (
        f"{_PERSONA}\n\n{_RESEARCH_PREFIX if deep else ''}"
        f"Here is your client's full portfolio right now:\n\n{facts}\n\n"
        f"Give your professional whole-portfolio review: overall posture, "
        f"concentration/risk assessment, and the most important concrete "
        f"actions this week (name specific tickers and levels). "
        f'Respond with ONLY a JSON object, no markdown, with these keys: '
        f'"summary" (string: overall take in 1-2 sentences max), '
        f'"insights" (array of 4-7 strings: portfolio health — one observation '
        f'per bullet on risk metrics, correlation/concentration, momentum, '
        f'citing the numbers), '
        f'"actions" (array of 3-5 strings: one concrete action per bullet — '
        f'ticker, what to do, size, and the exact level or trigger), '
        f'"risks" (array of 2-4 strings: one risk per bullet, each paired with '
        f'the specific tripwire signal to watch). '
        f'Every bullet must be a single self-contained sentence under 30 words. '
        f'No lead-in phrases, no numbering — the UI renders them as a list.'
    )
    raw, sid = _run_claude(prompt, research=deep)
    note = _parse_note("PORTFOLIO", "claude", raw) if raw else \
        _fallback_note("PORTFOLIO", facts, all_signals)
    if raw and sid:
        _remember_session(key, sid)
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
        f"{facts}\n\nMake the bull case for a near-term breakout AND state what would "
        f"invalidate it. Be specific about entry zone, the level that confirms the "
        f"breakout, and a stop. {_SCHEMA_HINT}"
    )
    raw, sid = _run_claude(prompt, research=deep)
    note = _parse_note(cand.symbol, "claude", raw) if raw else \
        _fallback_note(cand.symbol, facts, cand.signals)
    if raw and sid:
        _remember_session(key, sid)
    _cache[key] = (time.time(), note)
    return note


# ------------------------------------------------------------------ follow-up
_ASK_FMT = (
    'Respond with ONLY a JSON object, no markdown: '
    '{"answer": string (the direct answer to the question in 1-2 sentences), '
    '"points": array of 0-4 supporting bullet strings, each a single '
    'self-contained sentence under 25 words}. No lead-in phrases.'
)


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

    key = "portfolio:brief" if kind == "portfolio" else f"{kind}:{symbol}"
    research_note = _RESEARCH_PREFIX if deep else ""
    raw = sid = None
    prior = _sessions.get(key)
    if prior:
        raw, sid = _run_claude(
            f"{research_note}Client follow-up question: {question}\n\n{_ASK_FMT}",
            resume=prior, research=deep)

    if raw is None:
        # No live session — rebuild context and ask cold.
        from . import insights as insights_service
        from . import portfolio as pf_service
        if kind == "portfolio":
            summary, reports = pf_service.portfolio_summary()
            facts = _facts_from_portfolio(
                summary, reports,
                insights_service.compute_risk(reports),
                insights_service.build_alerts(reports))
        else:
            facts = _facts_from_report(pf_service.build_report(symbol))
        note = _cache.get(key)
        prior_note = ""
        if note:
            n = note[1]
            prior_note = ("\n\nYour previous advice to this client:\n"
                          f"Take: {n.summary}\nActions: " + "; ".join(n.actions) +
                          "\nRisks: " + "; ".join(n.risks))
        prompt = (f"{_PERSONA}\n\n{research_note}"
                  f"The client's current data:\n\n{facts}{prior_note}"
                  f"\n\nClient question: {question}\n\n{_ASK_FMT}")
        raw, sid = _run_claude(prompt, research=deep)

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
            "answer": answer, "points": points}
