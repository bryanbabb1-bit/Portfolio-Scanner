"""Agent debate endpoints.

A debate is six sequential-ish Claude CLI calls (two concurrent rounds plus a
judge), which is far past the ~100s Cloudflare tunnel ceiling. So POST returns
a job id immediately and the client polls, exactly like deep advisor asks.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import debate as debate_service
from ..services import jobs, market_data

router = APIRouter(prefix="/api", tags=["debate"])


@router.get("/debate")
def list_debates(limit: int = 20):
    """Recent rulings across all symbols (no transcripts)."""
    return {"results": debate_service.history(limit)}


@router.get("/debate/scorecard")
def verdict_scorecard(days: int = 30):
    """Trailing 5-day grade on every ruling — was the desk right?"""
    from ..services import verdict_score
    return verdict_score.scorecard(days=days)


@router.get("/debate/nightly")
def nightly_preload(include_queue: bool = False):
    """What the desk pre-loaded overnight, plus tonight's ranked queue.

    The queue is shown so the choice is inspectable: you can see WHY a name is
    next rather than trusting that it is."""
    from ..services import nightly, portfolio as pf

    # Last night's rulings are a file read and return instantly. Scoring the
    # queue needs a full portfolio scan, which is far too slow to sit in front
    # of a homepage panel — so it is opt-in. The panel asks for it only when
    # there are no rulings to show yet.
    queue: list = []
    if include_queue:
        try:
            _, reports = pf.portfolio_summary()
            live = [r for r in reports if getattr(r.quote, "source", "") == "live"]
            queue = nightly.score_candidates(live)[: nightly.MAX_PER_NIGHT * 2]
        except Exception as exc:
            print(f"[debate] nightly queue failed: {exc!r}")
    return {"last": nightly.last_result(), "queue": queue,
            "max_per_night": nightly.MAX_PER_NIGHT,
            "redebate_after_days": nightly.REDEBATE_AFTER_DAYS}


@router.post("/debate/nightly/run")
def run_nightly(force: bool = True):
    """Force the overnight pre-load now instead of waiting for the window."""
    from ..services import nightly
    return nightly.maybe_run(force=force) or {"ran": [], "note": "not due"}


@router.get("/debate/{symbol}")
def get_debate(symbol: str):
    """The cached debate for a symbol, or null when the desk hasn't sat."""
    return debate_service.get_cached(symbol.upper(), max_age=10**9)


@router.post("/debate/{symbol}")
def start_debate(symbol: str, force: bool = False):
    """Convene the desk. Returns {job_id} — poll /api/debate/job/{id}.

    When a fresh debate is already cached this returns it inline with
    job_id=null, so the UI doesn't spend six model calls to redraw a panel."""
    sym = symbol.upper()
    if not force:
        cached = debate_service.get_cached(sym)
        if cached:
            return {"job_id": None, "result": cached, "cached": True}
    try:
        market_data.warm_cache([sym])
    except Exception:
        pass
    job_id = jobs.submit(debate_service.convene, sym, force=True)
    return {"job_id": job_id, "result": None, "cached": False}


@router.get("/debate/job/{job_id}")
def debate_job(job_id: str):
    """Poll a running debate. Returns {status: pending|done|error, result}."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return job
