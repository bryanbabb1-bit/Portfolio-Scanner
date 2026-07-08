"""Portfolio Scanner API.

FastAPI backend powering the Portfolio Scanner hub: portfolio scanning, technical
analysis, a breakout radar, and an AI "senior Schwab advisor" driven by the local
Claude subscription in headless mode.
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import (
    advisor, breakouts, conviction, devices, discovery, graph, insights,
    journal, pins, plan, portfolio, runner, scan, strategy, summary,
    watchpoints,
)

app = FastAPI(
    title="Portfolio Scanner API",
    description="Scan your portfolio for news, trends, ratings, technicals and "
                "breakouts, with risk analytics, alerts and a senior-advisor AI layer.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router)
app.include_router(scan.router)
app.include_router(breakouts.router)
app.include_router(advisor.router)
app.include_router(insights.router)
app.include_router(discovery.router)
app.include_router(conviction.router)
app.include_router(pins.router)
app.include_router(plan.router)
app.include_router(graph.router)
app.include_router(journal.router)
app.include_router(strategy.router)
app.include_router(watchpoints.router)
app.include_router(runner.router)
app.include_router(devices.router)
app.include_router(summary.router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """Log every unhandled error with a traceback (surfaced in server.log)
    and return the reason instead of a bare 500."""
    print(f"[500] {request.method} {request.url.path}")
    traceback.print_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "data_mode": settings.DATA_MODE,
        "advisor_enabled": settings.ADVISOR_ENABLED,
    }


@app.get("/")
def root():
    return {"service": "portfolio-scanner", "docs": "/docs"}


# --------------------------------------------------------------- heartbeat
# The watchdog must not depend on a client being open. This background thread
# runs the scan itself every ~2 min so action pushes fire and the morning/EOD
# briefs post on time even when the app is closed. scan() early-returns cheaply
# when the market is shut, so off-hours this is a near no-op.
def _heartbeat() -> None:
    import time as _t
    from .services import conviction
    _t.sleep(15)  # let startup settle
    while True:
        try:
            conviction.scan()
        except Exception as exc:  # never let the loop die
            print(f"[heartbeat] scan failed: {exc!r}")
        _t.sleep(120)


@app.on_event("startup")
def _start_heartbeat() -> None:
    if settings.DATA_MODE == "mock":
        return  # tests / offline — no autonomous scanning
    import threading
    threading.Thread(target=_heartbeat, name="watchdog-heartbeat", daemon=True).start()
    print("[heartbeat] watchdog heartbeat started (scan every 120s)")
