"""Clean Sheet endpoints — the from-scratch book, and the diff against reality."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import cleansheet as cs
from ..services import jobs

router = APIRouter(prefix="/api", tags=["cleansheet"])


@router.get("/cleansheet")
def get_cleansheet():
    """The last build, or null. Never constructs — that costs a model call."""
    return cs.last_result()


@router.post("/cleansheet")
def start_cleansheet(force: bool = True):
    """Build the from-scratch portfolio. Returns {job_id} to poll.

    One best-model call plus a market-wide scan, so it runs as a job and is
    cached for a day: a from-scratch view does not change hourly."""
    if not force:
        cached = cs.last_result(cs.CACHE_TTL)
        if cached:
            return {"job_id": None, "result": cached, "cached": True}
    return {"job_id": jobs.submit(cs.build, force=True), "result": None,
            "cached": False}


@router.get("/cleansheet/job/{job_id}")
def cleansheet_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return job
