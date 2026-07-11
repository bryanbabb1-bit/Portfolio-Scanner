"""Options endpoints — a defined-risk options trade for a conviction."""
from __future__ import annotations

import re
import traceback

from fastapi import APIRouter, HTTPException

from ..services import options as opt_service
from ..services import portfolio as pf_service
from ..services import stance as stance_service

router = APIRouter(prefix="/api/options", tags=["options"])

_BEARISH = {"SELL", "TRIM", "AVOID"}


def _price(s) -> float | None:
    if not s:
        return None
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", str(s))
    return float(m.group(1).replace(",", "")) if m else None


def _build(sym: str, side: str | None, horizon: int):
    """Shared: resolve side + target from the stance and build the trade."""
    report = pf_service.build_report(sym)
    st = stance_service.get(sym) or {}
    action = str(st.get("action") or "").upper()
    bearish = action in _BEARISH
    chosen = (side or ("put" if bearish else "call")).lower()
    spot = report.quote.price
    tgt = _price(st.get("target")) or report.analyst.mean_target
    if not tgt or (chosen == "call" and tgt <= spot) or (chosen == "put" and tgt >= spot):
        tgt = round(spot * (0.82 if chosen == "put" else 1.22), 2)
    tgt = round(tgt, 2)
    trade = opt_service.suggest(sym, chosen, target=tgt, horizon_days=horizon)
    return report, action, chosen, spot, tgt, trade


@router.get("/{symbol}")
def option_idea(symbol: str, side: str | None = None, horizon: int = 120):
    """The recommended defined-risk options trade for `symbol`, aligned to the
    advisor's standing stance (bullish -> long call, bearish -> long put) with a
    target from the stance / analyst consensus. Deterministic — no Claude."""
    sym = symbol.upper()
    try:
        report, action, chosen, spot, tgt, trade = _build(sym, side, horizon)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Could not load {sym}: {exc}")
    return {
        "symbol": sym, "spot": round(spot, 2), "side": chosen,
        "stance": action or None, "held": report.market_value is not None,
        "target": tgt, "trade": trade,
    }


@router.get("/{symbol}/thesis")
def option_thesis(symbol: str, side: str | None = None, horizon: int = 120):
    """The trade PLUS the advisor's framing (thesis, contract fit, sizing, risk).
    Runs one Claude call — fetched on demand, not automatically."""
    sym = symbol.upper()
    try:
        report, action, chosen, spot, tgt, trade = _build(sym, side, horizon)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Could not load {sym}: {exc}")
    if not trade:
        return {"symbol": sym, "side": chosen, "target": tgt, "trade": None, "advice": None}
    from ..services import advisor
    advice = advisor.advise_option(sym, trade, chosen, tgt)
    return {"symbol": sym, "spot": round(spot, 2), "side": chosen,
            "stance": action or None, "target": tgt, "trade": trade, "advice": advice}
