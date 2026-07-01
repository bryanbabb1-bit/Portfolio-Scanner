"""Portfolio + report assembly."""
from __future__ import annotations

import json

from ..config import settings
from ..models.schemas import (
    PortfolioSummary,
    StockReport,
)
from . import market_data
from .technical import build_quote, compute_indicators, derive_signals


def load_portfolio() -> dict:
    with open(settings.PORTFOLIO_FILE) as f:
        return json.load(f)


def _holding_map() -> dict[str, dict]:
    pf = load_portfolio()
    return {h["symbol"].upper(): h for h in pf.get("holdings", [])}


def build_report(symbol: str, theme: str | None = None) -> StockReport:
    md = market_data.get_market_data(symbol)
    ind = compute_indicators(md.history)
    quote = build_quote(md, ind)
    signals = derive_signals(quote, ind)

    # Analyst view with computed upside.
    a = md.analyst or {}
    upside = None
    if a.get("mean_target") and quote.price:
        upside = round((a["mean_target"] / quote.price - 1) * 100, 2)
    from ..models.schemas import AnalystView, NewsItem

    analyst = AnalystView(
        recommendation=a.get("recommendation"),
        mean_target=a.get("mean_target"),
        high_target=a.get("high_target"),
        low_target=a.get("low_target"),
        num_analysts=a.get("num_analysts"),
        upside_pct=upside,
    )
    news = [NewsItem(**n) for n in (md.news or [])[:6]]

    report = StockReport(
        symbol=md.symbol,
        theme=theme,
        quote=quote,
        indicators=ind,
        analyst=analyst,
        news=news,
        signals=signals,
    )

    # Attach position economics if held.
    held = _holding_map().get(md.symbol)
    if held:
        shares = float(held.get("shares", 0))
        cost = float(held.get("cost_basis", 0))
        mv = round(shares * quote.price, 2)
        cost_total = shares * cost
        report.shares = shares
        report.cost_basis = cost
        report.market_value = mv
        report.unrealized_pl = round(mv - cost_total, 2)
        report.unrealized_pl_pct = round(
            ((quote.price / cost - 1) * 100) if cost else 0.0, 2
        )
        if not report.theme:
            report.theme = held.get("theme")
    return report


def portfolio_summary() -> tuple[PortfolioSummary, list[StockReport]]:
    pf = load_portfolio()
    reports: list[StockReport] = []
    for h in pf.get("holdings", []):
        reports.append(build_report(h["symbol"], h.get("theme")))

    total_mv = sum(r.market_value or 0 for r in reports)
    total_cost = sum((r.cost_basis or 0) * (r.shares or 0) for r in reports)
    total_pl = total_mv - total_cost
    day_change = sum((r.quote.change or 0) * (r.shares or 0) for r in reports)
    prev_value = total_mv - day_change

    by_theme: dict[str, float] = {}
    for r in reports:
        by_theme[r.theme or "Other"] = round(
            by_theme.get(r.theme or "Other", 0) + (r.market_value or 0), 2
        )

    source = "mock" if any(r.quote.source == "mock" for r in reports) else "live"
    summary = PortfolioSummary(
        total_market_value=round(total_mv, 2),
        total_cost=round(total_cost, 2),
        total_unrealized_pl=round(total_pl, 2),
        total_unrealized_pl_pct=round((total_pl / total_cost * 100) if total_cost else 0, 2),
        day_change=round(day_change, 2),
        day_change_pct=round((day_change / prev_value * 100) if prev_value else 0, 2),
        positions=len(reports),
        source=source,
        by_theme=by_theme,
    )
    return summary, reports
