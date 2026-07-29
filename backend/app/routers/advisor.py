"""AI advisor endpoints (headless Claude via the local subscription)."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..models.schemas import AskRequest, RecommendRequest
from ..services import advisor as advisor_service
from ..services import chat as chat_service
from ..services import jobs as jobs_service
from ..services import discovery as discovery_service
from ..services import insights as insights_service
from ..services import market_data, screener, themes
from ..services import portfolio as pf_service

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


def _build_brief(force: bool, deep: bool):
    """Assemble the facts and run the brief. Slow by nature — one Claude call
    plus a market-wide discovery sweep — so callers run it as a job."""
    summary, reports = pf_service.portfolio_summary()
    risk = insights_service.compute_risk(reports)
    alerts = insights_service.build_alerts(reports)
    try:
        # Buy-side context: the advisor should weigh new-name opportunities,
        # not just prune the existing book.
        candidates = discovery_service.discover(min_score=0, limit=8)["results"]
    except Exception:
        candidates = None
    return advisor_service.advise_portfolio(
        summary, reports, risk, alerts, force=force, deep=deep,
        candidates=candidates)


@router.get("/portfolio")
def advise_portfolio(force: bool = False, deep: bool = False):
    """Whole-book brief, synchronously. Safe only for a CACHE HIT.

    Generating one is a Claude call that now also produces the staged plan, so
    it regularly runs past the tunnel's ~100s edge timeout and 524s. Clients
    should POST /portfolio/start and poll; this endpoint stays for the cached
    path and for local (non-tunnelled) use."""
    try:
        return _build_brief(force, deep)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Brief failed: {exc}")


@router.post("/portfolio/start")
def advise_portfolio_start(force: bool = False, deep: bool = False):
    """Kick off the brief in the background; poll /job/{job_id}.

    Same discipline as /ask/start: keep every HTTP request short so a long
    generation survives the tunnel instead of dying at the edge."""
    return {"job_id": jobs_service.submit(_build_brief, force, deep),
            "status": "pending"}


@router.post("/stock/{symbol}/start")
def advise_stock_start(symbol: str, force: bool = False, deep: bool = False):
    """Backgrounded single-stock read — deep=true can run several minutes."""
    def _run():
        return advisor_service.advise_stock(
            pf_service.build_report(symbol.upper()), force=force, deep=deep)
    return {"job_id": jobs_service.submit(_run), "status": "pending"}


@router.get("/job/{job_id}")
def advisor_job(job_id: str):
    """Poll any backgrounded advisor call.

    status: pending | done | error | gone. 'gone' means the id is unknown —
    usually a backend restart dropped the worker; the client just re-asks."""
    job = jobs_service.get(job_id)
    if job is None:
        return {"status": "gone"}
    if job["status"] == "error":
        return {"status": "error", "error": job["error"]}
    if job["status"] == "done":
        return {"status": "done", "result": job["result"]}
    return {"status": "pending"}


@router.get("/stay-the-course")
def stay_the_course():
    """Grounded 'hold the course' read for the long game — reassurance when the
    book is steady, a pointer to the plan when it's not. Alerts are untouched."""
    from ..services import staycourse as staycourse_service
    try:
        summary, reports = pf_service.portfolio_summary()
        risk = insights_service.compute_risk(reports)
        alerts = insights_service.build_alerts(reports)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Portfolio read failed: {exc}")
    read = staycourse_service.read(summary, reports, risk, alerts)
    return advisor_service.advise_stay_course(read, summary, reports, risk)


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


def _validate_ask(req: AskRequest) -> tuple[str, str | None, str]:
    """Shared validation → (kind, symbol|None, question)."""
    if req.kind not in ("portfolio", "strategy") and not (req.symbol or "").strip():
        raise HTTPException(status_code=422, detail="symbol required for this kind")
    return req.kind, (req.symbol or "").strip().upper() or None, req.question.strip()


@router.post("/ask")
def ask(req: AskRequest):
    """Follow-up Q&A on a prior advisor note — resumes the same Claude
    conversation so the brief and data stay in context. Synchronous: fine for
    quick (non-deep) asks. Deep asks should use /ask/start + /ask/status so the
    Cloudflare tunnel's ~100s edge timeout can't 524 a long research run."""
    kind, symbol, question = _validate_ask(req)
    try:
        return advisor_service.ask(kind, symbol, question, deep=req.deep)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Ask failed: {exc}")


@router.post("/ask/start")
def ask_start(req: AskRequest):
    """Kick off a follow-up ask in the background and return a job id at once.
    The client polls /ask/status/{job_id}. This keeps every HTTP request short,
    so deep web-research asks (1-5 min) survive the tunnel's 100s edge timeout
    instead of 524'ing."""
    kind, symbol, question = _validate_ask(req)
    job_id = jobs_service.submit(
        advisor_service.ask, kind, symbol, question, deep=req.deep)
    return {"job_id": job_id, "status": "pending"}


@router.get("/chat")
def chat_thread(kind: str = "portfolio", symbol: str | None = None,
                limit: int = chat_service.KEEP_TURNS):
    """The recorded conversation for a context, oldest first.

    Served so the thread is the SAME on every device — it used to live only in
    one browser's localStorage, so a conversation started on the phone was
    invisible on the desktop."""
    key = chat_service.key_for(kind, (symbol or "").strip().upper() or None)
    return {"kind": kind, "symbol": symbol,
            "turns": chat_service.recent(key, max(1, min(limit, chat_service.KEEP_TURNS)))}


@router.delete("/chat")
def chat_clear(kind: str = "portfolio", symbol: str | None = None):
    """Forget one conversation. Clearing the thread in the UI clears it here too,
    so 'clear' means forgotten rather than hidden on this device."""
    key = chat_service.key_for(kind, (symbol or "").strip().upper() or None)
    return {"cleared": chat_service.clear(key)}


@router.get("/ask/status/{job_id}")
def ask_status(job_id: str):
    """Poll a backgrounded ask. status: pending | done | error | gone.
    'gone' means the job id is unknown — usually a backend restart dropped the
    in-flight worker; the client should just re-ask."""
    job = jobs_service.get(job_id)
    if job is None:
        return {"status": "gone"}
    if job["status"] == "error":
        return {"status": "error", "error": job["error"]}
    if job["status"] == "done":
        return {"status": "done", "result": job["result"]}
    return {"status": "pending"}


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
