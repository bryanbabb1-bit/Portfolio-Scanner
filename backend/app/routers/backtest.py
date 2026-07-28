"""Backtest endpoints. The replay is CPU-bound over the whole universe, so it
runs as a job and the last completed result is served from disk."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import backtest as bt
from ..services import jobs

router = APIRouter(prefix="/api", tags=["backtest"])


@router.get("/backtest")
def get_backtest():
    """The most recent completed run, or null if it has never been run."""
    return bt.last_result()


@router.post("/backtest")
def start_backtest(years: int = 5, limit: int | None = None):
    """Replay every conviction rule over `years` of history. Returns {job_id}."""
    if not 1 <= years <= 10:
        raise HTTPException(status_code=422, detail="years must be 1-10")
    return {"job_id": jobs.submit(bt.run, years=years, limit=limit)}


@router.get("/backtest/job/{job_id}")
def backtest_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return job
