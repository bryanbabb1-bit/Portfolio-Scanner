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
from .routers import advisor, breakouts, discovery, insights, portfolio, scan

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
