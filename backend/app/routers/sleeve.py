"""The trading sleeve: tickets, fills, exits, and the sleeve's own record.

The heartbeat drives the lifecycle; these endpoints are how Bryan answers it
(filled / passed / sold) and how the blotter reads it.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import sleeve

router = APIRouter(prefix="/api/sleeve", tags=["sleeve"])


class Fill(BaseModel):
    price: float
    shares: float | None = None


class Close(BaseModel):
    price: float
    reason: str = "manual"


class ManualTicket(BaseModel):
    symbol: str
    entry: float
    stop: float
    target: float | None = None
    engine: str = "manual"
    why: list[str] = []
    headline: str = ""


@router.get("")
def get_state():
    """The blotter: config, capital, equity, every ticket, the scorecard."""
    return sleeve.state()


@router.get("/config")
def get_config():
    return sleeve.config()


@router.put("/config")
def put_config(changes: dict):
    return sleeve.set_config(changes)


@router.post("/run")
def run(force: bool = False):
    """Force one heartbeat pass (issue / expire / manage) for inspection."""
    return sleeve.maybe_run(force=force) or {"ran": False, "reason": "disabled"}


@router.post("/tickets")
def manual_ticket(body: ManualTicket):
    """Ticket a name by hand — from the Tape, a chart, or a hunch. Sized by
    the same risk math as everything else."""
    if body.engine not in sleeve.ENGINES:
        raise HTTPException(400, f"engine must be one of {sleeve.ENGINES}")
    t = sleeve.issue(body.symbol, body.engine, body.entry, body.stop,
                     target=body.target, why=body.why, headline=body.headline,
                     push_it=False)
    if not t:
        raise HTTPException(409, "refused: sleeve disabled, duplicate open ticket, "
                                 "bad levels, or nothing to size against")
    return t


@router.post("/tickets/{ticket_id}/fill")
def fill(ticket_id: str, body: Fill):
    try:
        return sleeve.confirm_fill(ticket_id, body.price, body.shares)
    except KeyError:
        raise HTTPException(404, "no such ticket")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/tickets/{ticket_id}/pass")
def pass_it(ticket_id: str):
    try:
        return sleeve.pass_ticket(ticket_id)
    except KeyError:
        raise HTTPException(404, "no such ticket")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/tickets/{ticket_id}/close")
def close(ticket_id: str, body: Close):
    try:
        return sleeve.close(ticket_id, body.price, body.reason)
    except KeyError:
        raise HTTPException(404, "no such ticket")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
