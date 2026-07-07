"""AI advisor endpoints (headless Claude via the local subscription)."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..models.schemas import AskRequest, RecommendRequest
from ..services import advisor as advisor_service
from ..services import discovery as discovery_service
from ..services import insights as insights_service
from ..services import market_data, screener, themes
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.get("/portfolio")
def advise_portfolio(force: bool = False, deep: bool = False):
    """Whole-book senior-advisor brief. deep=true adds live web research."""
    try:
        summary, reports = pf_service.portfolio_summary()
        risk = insights_service.compute_risk(reports)
        alerts = insights_service.build_alerts(reports)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Portfolio read failed: {exc}")
    try:
        # Buy-side context: the advisor should weigh new-name opportunities,
        # not just prune the existing book.
        candidates = discovery_service.discover(min_score=0, limit=8)["results"]
    except Exception:
        candidates = None
    return advisor_service.advise_portfolio(
        summary, reports, risk, alerts, force=force, deep=deep,
        candidates=candidates)


@router.post("/recommend")
def recommend(req: RecommendRequest):
    """What should the client DO about a notification event — portfolio-aware,
    always ends in a clear action (may be Hold). Cached 1h."""
    try:
        return advisor_service.recommend(
            req.symbol.upper(), req.event.strip(), req.kind)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Recommend failed: {exc}")


@router.get("/last")
def last_note(kind: str = "portfolio", symbol: str | None = None):
    """The most recent stored advisor note for a context (no Claude call) —
    used to restore a brief after navigating away."""
    key = "portfolio:brief" if kind == "portfolio" \
        else f"{kind}:{(symbol or '').upper()}"
    note = advisor_service.get_last_note(key)
    if not note:
        raise HTTPException(status_code=404, detail="no prior note")
    return note


@router.post("/ask")
def ask(req: AskRequest):
    """Follow-up Q&A on a prior advisor note — resumes the same Claude
    conversation so the brief and data stay in context."""
    if req.kind not in ("portfolio", "strategy") and not (req.symbol or "").strip():
        raise HTTPException(status_code=422, detail="symbol required for this kind")
    try:
        return advisor_service.ask(
            req.kind, (req.symbol or "").strip().upper() or None,
            req.question.strip(), deep=req.deep)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Ask failed: {exc}")


@router.get("/stock/{symbol}")
def advise_stock(symbol: str, force: bool = False, deep: bool = False):
    """Senior-advisor read for one stock. deep=true adds live web research."""
    try:
        report = pf_service.build_report(symbol.upper())
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Report failed: {exc}")
    return advisor_service.advise_stock(report, force=force, deep=deep)


@router.get("/breakout/{symbol}")
def advise_breakout(symbol: str, force: bool = False, deep: bool = False):
    """The bull case (and invalidation) for a breakout candidate."""
    md = market_data.get_market_data(symbol.upper())
    pf = pf_service.load_portfolio()
    manual = next(
        (i.get("theme") for i in pf.get("holdings", []) + pf.get("watchlist", [])
         if i["symbol"].upper() == symbol.upper()),
        None,
    )
    cand = screener.evaluate(
        symbol.upper(), themes.resolve(symbol.upper(), manual), md)
    return advisor_service.advise_breakout(cand, force=force, deep=deep)
