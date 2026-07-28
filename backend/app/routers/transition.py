"""Transition plan endpoints — the sequenced path from current book to target."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import jobs
from ..services import transition as tr

router = APIRouter(prefix="/api", tags=["transition"])


@router.get("/transition")
def get_transition():
    """The saved plan, with the gap recomputed live so drift stays current."""
    plan = tr.last_plan()
    if not plan:
        return None
    try:
        plan = {**plan, "analysis": tr.analyse()}
    except Exception:
        pass          # keep the stored snapshot rather than failing the page
    return plan


@router.get("/transition/analysis")
def get_analysis():
    """The deterministic half only — gap, funding sources, targets. No model."""
    try:
        return tr.analyse()
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
