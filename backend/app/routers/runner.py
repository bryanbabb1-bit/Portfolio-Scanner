"""Runner Radar endpoint — explosive low-float setups (the MGRT pattern)."""
from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException

from ..services import runner

router = APIRouter(prefix="/api", tags=["runner"])


@router.get("/runners")
def runners(min_score: float = 0.0, limit: int = 40, extra: str = ""):
    """Score the curated low-float / high-velocity universe (+ comma-separated
    `extra` tickers the user is watching) on explosive-setup DNA."""
    try:
        tickers = [t for t in extra.split(",") if t.strip()]
        return runner.radar(min_score=min_score, limit=limit, extra=tickers)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Runner radar failed: {exc}")


@router.get("/lowfloat")
def low_float_screen(force: bool = False, relax_float: bool = False,
                     max_price: float | None = None,
                     min_price: float | None = None,
                     min_rvol: float | None = None,
                     min_volume: int | None = None,
                     max_float: int | None = None,
                     max_cap: int | None = None):
    """The five-filter momentum screen. Every threshold is overridable, so
    tightening back to the originally stated screen is a query parameter."""
    from ..services import lowfloat
    return lowfloat.screen(force=force, relax_float=relax_float,
                           max_price=max_price, min_price=min_price,
                           min_rvol=min_rvol,
                           min_volume=min_volume, max_float=max_float,
                           max_cap=max_cap)


@router.get("/squeeze")
def squeeze_setups(force: bool = False, limit: int = 25):
    """Pre-ignition squeeze conditions — fuel and constraint, before the spark."""
    from ..services import squeeze
    return squeeze.screen(force=force, limit=limit)


@router.get("/reclaim")
def reclaim_setups(force: bool = False, limit: int = 25,
                   max_symbols: int | None = None):
    """Beaten down, stopped falling, just reclaimed the 20-day on volume.

    Scans the whole US listed market (~5,900 names) via bulk download.
    max_symbols caps the walk for a quick look."""
    from ..services import reclaim
    return reclaim.screen(force=force, limit=limit, max_symbols=max_symbols)
