"""Risk desk endpoints: the standing limits, open risk, and pre-trade sizing."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import PositionPlan, RiskDesk
from ..services import insights as insights_service
from ..services import market_data
from ..services import portfolio as pf_service
from ..services import risk as risk_service

router = APIRouter(prefix="/api", tags=["risk"])


def _warm() -> None:
    pf = pf_service.load_portfolio()
    symbols = [h["symbol"] for h in pf.get("holdings", [])]
    market_data.warm_cache(symbols + [insights_service.BENCHMARK])


@router.get("/risk", response_model=RiskDesk)
def get_risk():
    """Position sizing budget, stops, daily limits, open risk and exposure."""
    try:
        _warm()
        return risk_service.risk_desk()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Risk desk failed: {exc}")


@router.get("/risk/size/{symbol}", response_model=PositionPlan)
def size_position(symbol: str):
    """How much of `symbol` to buy, given the stop distance and risk budget.

    Works for any symbol — held, watched, or brand new."""
    sym = symbol.upper()
    try:
        market_data.warm_cache([sym])
        report = pf_service.build_report(sym)
        summary, _ = pf_service.portfolio_summary()
        return risk_service.plan_for(
            report, summary.total_market_value or 0.0, summary.cash
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sizing failed for {sym}: {exc}")
