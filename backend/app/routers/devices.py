"""Device registration for push notifications (the native app calls these)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import DeviceRegister
from ..services import push

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("")
def register_device(req: DeviceRegister):
    try:
        entry = push.register(req.token, req.platform)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"registered": entry["token"], "count": len(push.tokens())}


@router.delete("")
def unregister_device(req: DeviceRegister):
    return {"removed": push.unregister(req.token)}


@router.post("/test")
def test_push():
    """Fire a test push to every registered device — proves the loop end to end."""
    if not push.tokens():
        raise HTTPException(status_code=404, detail="no devices registered")
    return push.send(
        "Watchdog test",
        "Push is wired up. This is how a slap will reach you.",
        data={"type": "test"})
