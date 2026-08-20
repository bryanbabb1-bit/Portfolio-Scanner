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
    advisor,
    backtest,
    bigmoves,
    book,
    breakouts,
    catalysts,
    conviction,
    debate,
    devices,
    filings,
    discovery,
    graph,
    insights,
    journal,
    learning,
    options,
    pins,
    plan,
    portfolio,
    risk,
    runner,
    scan,
    summary,
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
app.include_router(options.router)
app.include_router(journal.router)
app.include_router(watchpoints.router)
app.include_router(runner.router)
app.include_router(devices.router)
app.include_router(summary.router)
app.include_router(risk.router)
app.include_router(debate.router)
app.include_router(backtest.router)
app.include_router(learning.router)
app.include_router(book.router)
app.include_router(catalysts.router)
app.include_router(filings.router)
app.include_router(bigmoves.router)


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
        # The thesis book manages itself: fills staged orders at the open,
        # trails and cuts per its rules, marks once a day. Early-returns cheaply
        # outside market hours and after it has already run today.
        try:
            from .services import thesis
            result = thesis.maybe_run()
            if result and (result["filled"] or result["stop_actions"]):
                print(f"[heartbeat] thesis book: {result}")
        except Exception as exc:
            print(f"[heartbeat] thesis book failed: {exc!r}")
        # Overnight desk pre-load: a few high-priority names debated after the
        # close so the rulings are waiting in the morning. Early-returns outside
        # its window and after it has run for the day, so this is free by day.
        # The catalyst map is a daily registry read, not a market job — warm it
        # so the Today tab never waits ~60s on clinicaltrials.gov mid-render.
        try:
            from .services import catalysts
            catalysts.get()
        except Exception as exc:
            print(f"[heartbeat] catalyst map failed: {exc!r}")
        # Material filings — this one is also the notifier: get() pushes the
        # first time it sees a high-severity 8-K on a name in the book.
        try:
            from .services import filings
            filings.get()
        except Exception as exc:
            print(f"[heartbeat] filings failed: {exc!r}")
        # Whole-market watch. Cheap (a screener call, cached to the heartbeat's
        # own cadence) and it is the thing that pushes when something enormous
        # happens to a name nobody in this book owns.
        try:
            from .services import bigmoves
            bigmoves.scan()
        except Exception as exc:
            print(f"[heartbeat] bigmoves failed: {exc!r}")
        try:
            from .services import nightly
            pre = nightly.maybe_run()
            if pre and pre.get("ran"):
                print(f"[heartbeat] desk pre-loaded: "
                      f"{[d['symbol'] for d in pre['ran']]}")
        except Exception as exc:
            print(f"[heartbeat] nightly desk failed: {exc!r}")
        _t.sleep(120)


@app.on_event("startup")
def _start_heartbeat() -> None:
    if settings.DATA_MODE == "mock":
        return  # tests / offline — no autonomous scanning
    import threading
    threading.Thread(target=_heartbeat, name="watchdog-heartbeat", daemon=True).start()
    print("[heartbeat] watchdog heartbeat started (scan every 120s)")
