"""AI advisor endpoints (headless Claude via the local subscription)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import AskRequest
from ..services import advisor as advisor_service
from ..services import insights as insights_service
from ..services import market_data, screener
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.get("/portfolio")
def advise_portfolio(force: bool = False):
    """Whole-book senior-advisor brief: posture, risk, concrete actions."""
    try:
        summary, reports = pf_service.portfolio_summary()
        risk = insights_service.compute_risk(reports)
        alerts = insights_service.build_alerts(reports)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Portfolio read failed: {exc}")
    return advisor_service.advise_portfolio(summary, reports, risk, alerts, force=force)


@router.post("/ask")
def ask(req: AskRequest):
    """Follow-up Q&A on a prior advisor note — resumes the same Claude
    conversation so the brief and data stay in context."""
    if req.kind != "portfolio" and not (req.symbol or "").strip():
        raise HTTPException(status_code=422, detail="symbol required for this kind")
    try:
        return advisor_service.ask(
            req.kind, (req.symbol or "").strip().upper() or None, req.question.strip())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ask failed: {exc}")


@router.get("/stock/{symbol}")
def advise_stock(symbol: str, force: bool = False):
    """Senior-advisor narrative + technical read for one stock."""
    try:
        report = pf_service.build_report(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report failed: {exc}")
    return advisor_service.advise_stock(report, force=force)


@router.get("/breakout/{symbol}")
def advise_breakout(symbol: str, force: bool = False):
    """The bull case (and invalidation) for a breakout candidate."""
    md = market_data.get_market_data(symbol.upper())
    pf = pf_service.load_portfolio()
    theme = next(
        (i.get("theme") for i in pf.get("holdings", []) + pf.get("watchlist", [])
         if i["symbol"].upper() == symbol.upper()),
        None,
    )
    cand = screener.evaluate(symbol.upper(), theme, md)
    return advisor_service.advise_breakout(cand, force=force)
