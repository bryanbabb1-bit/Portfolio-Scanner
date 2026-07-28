"""Transition plan endpoints — the sequenced path from current book to target."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import jobs
from ..services import transition as tr

router = APIRouter(prefix="/api", tags=["transition"])


@router.get("/transition")
def get_transition(refresh: bool = False):
    """The saved plan. Cheap by default so a page load can never fail.

    The gap and funding are recomputed (they only need the portfolio summary),
    but the per-target price lookup is NOT — that builds a full report for
    every acquisition target and made this endpoint slow enough to hit the
    tunnel's ~100s ceiling. A failed load rendered as "no plan", which invited
    a rebuild and silently replaced a plan that was saved perfectly well.
    Pass refresh=true for live target prices.
    """
    plan = tr.last_plan()
    if not plan:
        return None
    try:
        fresh = tr.analyse(full=refresh)
        stored = plan.get("analysis") or {}
        if not refresh:
            # Keep the prices captured when the plan was generated; only the
            # cheap parts are re-derived.
            fresh["acquire"] = stored.get("acquire") or fresh.get("acquire") or []
        plan = {**plan, "analysis": fresh}
    except Exception as exc:
        print(f"[transition] gap refresh failed, serving stored: {exc!r}")
    return plan


@router.get("/transition/analysis")
def get_analysis(full: bool = True):
    """The deterministic half only — gap, funding sources, targets. No model."""
    try:
        return tr.analyse(full=full)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")


@router.post("/transition")
def start_transition():
    """Build a sequenced plan. One model call, so it runs as a job."""
    return {"job_id": jobs.submit(tr.generate, force=True)}


@router.get("/transition/job/{job_id}")
def transition_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return job


@router.post("/transition/activate")
def activate():
    """Watchlist the targets and create the entry/exit watchpoints."""
    return tr.activate()


@router.post("/transition/step/{n}")
def step_done(n: int, done: bool = True):
    step = tr.set_step_done(n, done)
    if step is None:
        raise HTTPException(status_code=404, detail="No such step")
    return step
