"""Tiny in-memory background-job runner.

Why this exists: deep advisor questions run WebSearch/WebFetch and can take
1-5 minutes. The phone reaches the app through a Cloudflare tunnel
(watchdog.trueforecasting.app) whose edge kills ANY single request at ~100s
with a 524 — no server-side timeout can raise that ceiling. So instead of
holding one long request open, we run the work in a background thread and let
the client poll a fast status endpoint. Each poll returns instantly, so the
tunnel never sees a long request.

Jobs are process-local and NOT persisted: a backend restart drops in-flight
jobs. The client treats a missing job id as "gone" and simply re-asks — a
deliberately simple contract, since a restart also kills the worker thread.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

# job_id -> {status: "pending"|"done"|"error", result, error, created, finished}
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Drop finished jobs older than this so the map can't grow without bound.
_TTL_SECONDS = 3600


def _prune() -> None:
    """Evict finished jobs past their TTL. Caller need not hold the lock."""
    now = time.time()
    with _lock:
        stale = [
            jid for jid, j in _jobs.items()
            if j["status"] != "pending"
            and now - (j.get("finished") or j["created"]) > _TTL_SECONDS
        ]
        for jid in stale:
            _jobs.pop(jid, None)


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Run fn(*args, **kwargs) on a daemon thread; return a job id at once."""
    _prune()
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "created": time.time(),
            "finished": None,
        }

    def _run() -> None:
        try:
            out = fn(*args, **kwargs)
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(status="done", result=out, finished=time.time())
        except Exception as exc:  # noqa: BLE001 - surface any failure to the poller
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(status="error", error=str(exc),
                               finished=time.time())

    threading.Thread(target=_run, name=f"job-{job_id[:8]}", daemon=True).start()
    return job_id


def get(job_id: str) -> dict[str, Any] | None:
    """Return a snapshot {status, result, error} for job_id, or None if unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return {
            "status": job["status"],
            "result": job["result"],
            "error": job["error"],
        }
