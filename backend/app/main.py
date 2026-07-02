"""Portfolio Scanner API.

FastAPI backend powering the Portfolio Scanner hub: portfolio scanning, technical
analysis, a breakout radar, and an AI "senior Schwab advisor" driven by the local
Claude subscription in headless mode.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
