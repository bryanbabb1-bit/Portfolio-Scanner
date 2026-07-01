"""Portfolio + per-stock report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import PortfolioConfig
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def get_portfolio():
    """Full portfolio: summary metrics + a report card per holding."""
    summary, reports = pf_service.portfolio_summary()
    return {"summary": summary, "holdings": reports}


@router.get("/config")
def get_config():
    """Raw portfolio config (holdings, watchlist, themes)."""
    return pf_service.load_portfolio()


@router.put("/config", response_model=PortfolioConfig)
def put_config(cfg: PortfolioConfig):
    """Persist an edited portfolio config (holdings, watchlist, themes, persona).

    The body is validated by pydantic (symbols upper-cased, shares/cost >= 0)
    before being atomically written to portfolio.json.
    """
    try:
        saved = pf_service.save_portfolio(cfg.model_dump())
        return saved
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save config: {exc}")


@router.get("/quotes")
def get_quotes(symbols: str = ""):
    """Lightweight price lookup for a comma-separated list of symbols.

    Powers the live "$ value" column in the Settings editor so a fat-fingered
    share count is obvious the instant it's typed. Returns last close per symbol.
    """
    out: dict[str, dict] = {}
    for raw in symbols.split(","):
        sym = raw.strip().upper()
        if not sym or sym in out:
            continue
        try:
            md = pf_service.market_data.get_market_data(sym)
            out[sym] = {
                "price": round(float(md.history["Close"].iloc[-1]), 2),
                "source": md.source,
            }
        except Exception:
            out[sym] = {"price": None, "source": "error"}
    return {"quotes": out}


@router.get("/watchlist")
def get_watchlist():
    """Report cards for watched (non-held) names."""
    reports = pf_service.watchlist_reports()
    source = "mock" if any(r.quote.source == "mock" for r in reports) else "live"
    return {"count": len(reports), "source": source, "results": reports}


@router.get("/stock/{symbol}/history")
def get_stock_history(symbol: str, range: str = "6mo"):
    """OHLCV candles + SMA overlays for charting. range: 1mo|3mo|6mo|1y."""
    try:
        return pf_service.price_history(symbol.upper(), range)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load history: {exc}")


@router.get("/stock/{symbol}")
def get_stock(symbol: str):
    """Deep report for a single symbol (held or not)."""
    try:
        return pf_service.build_report(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not build report: {exc}")
