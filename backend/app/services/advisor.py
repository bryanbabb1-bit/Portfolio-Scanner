"""AI advisor service.

Generates a "senior Schwab financial advisor" narrative by shelling out to the
local `claude` CLI in headless print mode. This uses the signed-in Claude
subscription — no API key required. If the CLI is unavailable or times out, a
deterministic fallback narrative is produced from the computed signals so the
endpoint never hard-fails.
"""
from __future__ import annotations

import json
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

_PERSONA = (
    "You are a senior financial advisor at Charles Schwab with 20+ years of "
    "experience in technical analysis and the technology, AI, semiconductor, "
    "energy and data-center/compute sectors. You are pragmatic, risk-aware, and "
    "you never give generic disclaimers-only answers. You cite the specific "
    "numbers you are given."
)

_SCHEMA_HINT = (
    'Respond with ONLY a JSON object, no markdown, with these string keys: '
    '"summary" (2-3 sentence plain-English take), '
    '"technical_read" (what the indicators say, cite RSI/MACD/moving averages/volume), '
    '"recommendation" (accumulate / hold / trim / avoid, with reasoning and a level to watch), '
    '"risks" (key risks and invalidation level).'
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
        lines.append("Recent headlines: " + " | ".join(n.title for n in r.news[:3]))
    return "\n".join(lines)


def _run_claude(prompt: str) -> str | None:
    """Invoke `claude -p` headless; return the model's text result or None."""
    # On Windows the CLI is an npm `claude.CMD` shim — subprocess can't launch
    # it by bare name (WinError 2), so resolve the real path via PATH/PATHEXT.
    # The prompt goes over STDIN, not argv: multi-line args are mangled by the
    # cmd.exe batch layer, which silently truncates at the first newline.
    exe = shutil.which(settings.CLAUDE_BIN) or settings.CLAUDE_BIN
    cmd = [exe, "-p", "--output-format", "json"]
    if settings.CLAUDE_MODEL:
        cmd += ["--model", settings.CLAUDE_MODEL]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=settings.ADVISOR_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[advisor] claude CLI unavailable: {exc!r}")
        return None
    if proc.returncode != 0:
        print(f"[advisor] claude CLI rc={proc.returncode}: {proc.stderr[:300]}")
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout.strip() or None
    if payload.get("is_error"):
        return None
    return payload.get("result")


def _parse_note(symbol: str, engine: str, raw: str) -> AdvisorNote:
    summary = technical = rec = risks = ""
    text = raw.strip()
    # Extract JSON object if the model wrapped it in prose/fences.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            summary = obj.get("summary", "")
            technical = obj.get("technical_read", "")
            rec = obj.get("recommendation", "")
            risks = obj.get("risks", "")
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
        technical_read=technical,
        recommendation=rec,
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
        technical_read="; ".join(s.detail for s in signals) or "No strong signals.",
        recommendation=rec,
        risks="Automated fallback — verify against live data and position sizing "
              "before acting. Not personalized investment advice.",
        raw=facts,
    )


def advise_stock(report: StockReport, force: bool = False) -> AdvisorNote:
    key = f"stock:{report.symbol}"
    if not force:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < settings.ADVISOR_CACHE_TTL:
            return hit[1]

    facts = _facts_from_report(report)
    if not settings.ADVISOR_ENABLED:
        note = _fallback_note(report.symbol, facts, report.signals)
        _cache[key] = (time.time(), note)
        return note

    prompt = (
        f"{_PERSONA}\n\nHere is the current data for a stock a client holds or is "
        f"watching:\n\n{facts}\n\nAs their advisor, give your professional read. "
        f"{_SCHEMA_HINT}"
    )
    raw = _run_claude(prompt)
    note = _parse_note(report.symbol, "claude", raw) if raw else \
        _fallback_note(report.symbol, facts, report.signals)
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
    if alerts:
        lines.append("Active alerts: " + "; ".join(
            f"{a.symbol} {a.label} ({a.severity})" for a in alerts[:12]))
    return "\n".join(lines)


def advise_portfolio(summary: PortfolioSummary, reports: list[StockReport],
                     risk: RiskMetrics, alerts: list[PortfolioAlert],
                     force: bool = False) -> AdvisorNote:
    """One whole-book narrative: posture, risks, and concrete next actions."""
    key = "portfolio:brief"
    if not force:
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
        f"{_PERSONA}\n\nHere is your client's full portfolio right now:\n\n{facts}\n\n"
        f"Give your professional whole-portfolio review: overall posture, "
        f"concentration/risk assessment, and the 2-3 most important concrete "
        f"actions this week (name specific tickers and levels). "
        f'Respond with ONLY a JSON object, no markdown, with these string keys: '
        f'"summary" (2-3 sentence overall take), '
        f'"technical_read" (portfolio health: risk metrics, allocation, momentum), '
        f'"recommendation" (the 2-3 concrete actions, tickers and levels), '
        f'"risks" (the biggest risks to this book and what would signal them).'
    )
    raw = _run_claude(prompt)
    note = _parse_note("PORTFOLIO", "claude", raw) if raw else \
        _fallback_note("PORTFOLIO", facts, all_signals)
    _cache[key] = (time.time(), note)
    return note


def advise_breakout(cand: BreakoutCandidate, force: bool = False) -> AdvisorNote:
    key = f"breakout:{cand.symbol}"
    if not force:
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
        f"{_PERSONA}\n\nThis stock is flagged as a potential breakout candidate:\n\n"
        f"{facts}\n\nMake the bull case for a near-term breakout AND state what would "
        f"invalidate it. Be specific about entry zone, the level that confirms the "
        f"breakout, and a stop. {_SCHEMA_HINT}"
    )
    raw = _run_claude(prompt)
    note = _parse_note(cand.symbol, "claude", raw) if raw else \
        _fallback_note(cand.symbol, facts, cand.signals)
    _cache[key] = (time.time(), note)
    return note
