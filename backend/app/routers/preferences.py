"""Standing client preferences — what never to recommend, and what he wants."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import preferences as prefs_service

router = APIRouter(prefix="/api", tags=["preferences"])


class BlockRequest(BaseModel):
    symbol: str
    reason: str = ""


class ThemeRequest(BaseModel):
    theme: str


@router.get("/preferences")
def read_preferences():
    return prefs_service.get()


@router.post("/preferences/block")
def add_block(req: BlockRequest):
    return prefs_service.block(req.symbol, req.reason, source="manual")


@router.delete("/preferences/block/{symbol}")
def remove_block(symbol: str):
    return prefs_service.unblock(symbol)


@router.post("/preferences/want")
def add_want(req: ThemeRequest):
    return prefs_service.want(req.theme, source="manual")


@router.delete("/preferences/want/{theme}")
def remove_want(theme: str):
    return prefs_service.unwant(theme)
