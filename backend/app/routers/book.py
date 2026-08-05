"""The live thesis book — the simulation that is actually running.

Replaces the paper-trading lab, which was research: three models backtested,
none of which beat buy-and-hold, and the findings live in the commit history.
Keeping a page of dead backtests around would have made the app look like it
was doing something it stopped doing.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import market_data
from ..services import thesis as thesis_service

router = APIRouter(prefix="/api/book", tags=["book"])


def _quotes(symbols: list[str]) -> dict:
    out: dict = {}
    for sym in dict.fromkeys(symbols):
        try:
            md = market_data.get_price_data(sym)
            out[sym] = {"price": float(md.history["Close"].iloc[-1]),
                        "source": md.source}
        except Exception as exc:
            print(f"[book] quote failed for {sym}: {exc!r}")
    return out


@router.get("")
def get_book():
    """The book, marked to live prices.

    Live rather than cached on purpose: this is a real position being scored,
    and a stale mark on a concentrated book is how you fail to notice a thesis
    has broken.
    """
    book = thesis_service.load()
    held = [p["symbol"] for p in book.get("positions", []) if not p.get("closed")]
    return thesis_service.mark(book, _quotes(held))


@router.post("/run")
def run_book(force: bool = False):
    """Fill staged orders at the session open, then apply the stop rules.

    The heartbeat calls this itself; the endpoint exists so a run can be forced
    for inspection without waiting two minutes.
    """
    result = thesis_service.maybe_run(force=force)
    return result or {"ran": False, "reason": "outside market hours, "
                                              "already run today, or no live data"}


@router.get("/review")
def review():
    """What the book has learned so far."""
    return thesis_service.review()


@router.post("/review/run")
def run_review():
    """Force a learning review now rather than waiting for the cadence."""
    return thesis_service.learn(force=True)
