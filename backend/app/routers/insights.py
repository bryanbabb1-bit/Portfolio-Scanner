"""Portfolio intelligence endpoints: risk metrics, alerts, aggregated news."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..models.schemas import PortfolioInsights, PortfolioNewsItem
from ..services import insights as insights_service
from ..services import market_data
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api", tags=["insights"])


def _universe() -> list[dict]:
    pf = pf_service.load_portfolio()
    return list(pf.get("holdings", [])) + list(pf.get("watchlist", []))


@router.get("/insights", response_model=PortfolioInsights)
def get_insights():
    """Risk analytics (beta, vol, Sharpe, drawdown, concentration) + alerts."""
    try:
        symbols = [i["symbol"] for i in _universe()] + [insights_service.BENCHMARK]
        market_data.warm_cache(symbols)
        return insights_service.portfolio_insights()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Insights failed: {exc}")


@router.get("/news")
def get_news(limit: int = 40):
    """All recent headlines across holdings + watchlist, deduped and tagged."""
    universe = _universe()
    market_data.warm_cache([i["symbol"] for i in universe])

    by_title: dict[str, PortfolioNewsItem] = {}
    any_mock = False
    for item in universe:
        sym = item["symbol"].upper()
        try:
            md = market_data.get_market_data(sym)
        except Exception:
            continue
        any_mock = any_mock or md.source == "mock"
        for n in md.news or []:
            title = (n.get("title") or "").strip()
            if not title:
                continue
            existing = by_title.get(title)
            if existing:
                if sym not in existing.symbols:
                    existing.symbols.append(sym)
                continue
            by_title[title] = PortfolioNewsItem(
                title=title,
                symbols=[sym],
                publisher=n.get("publisher"),
                link=n.get("link"),
                published=str(n["published"]) if n.get("published") else None,
            )

    def sort_key(n: PortfolioNewsItem):
        oldest = pd.Timestamp.min.tz_localize("UTC")
        if not n.published:
            return oldest
        try:
            # Bare-numeric strings are Unix epochs from older cached payloads.
            if n.published.replace(".", "", 1).isdigit():
                return pd.to_datetime(float(n.published), unit="s", utc=True)
            ts = pd.to_datetime(n.published, utc=True)
            return oldest if pd.isna(ts) else ts
        except Exception:
            return oldest

    items = sorted(by_title.values(), key=sort_key, reverse=True)[:limit]
    return {
        "count": len(items),
        "source": "mock" if any_mock else "live",
        "results": items,
    }
