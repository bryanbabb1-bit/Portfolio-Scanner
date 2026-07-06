"""Push notifications via the Expo Push service.

The native app registers its Expo push token here; when the watchdog fires a
new conviction signal / watchpoint hit / runner ignition, we POST it to Expo's
push API (https://exp.host/--/api/v2/push/send) — no API key required, the
device token is the credential. This is what puts a slap in Bryan's pocket.

v1: the PC backend sends these while it's running. v2 (cloud watchdog) would
move the same call to an always-on worker.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "push_tokens.json"
_EXPO_URL = "https://exp.host/--/api/v2/push/send"
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        with open(_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_FILE, "w") as f:
        json.dump(items[-50:], f, indent=2)


def register(token: str, platform: str | None = None) -> dict:
    """Store an Expo push token (idempotent). Bad tokens are refused."""
    token = (token or "").strip()
    if not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")):
        raise ValueError("not a valid Expo push token")
    with _lock:
        items = _load()
        for t in items:
            if t["token"] == token:
                t["seen_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _save(items)
                return t
        entry = {
            "token": token,
            "platform": platform or "ios",
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        items.append(entry)
        _save(items)
        return entry


def unregister(token: str) -> bool:
    with _lock:
        items = _load()
        kept = [t for t in items if t["token"] != token]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def tokens() -> list[str]:
    return [t["token"] for t in _load()]


def _post(messages: list[dict]) -> dict | None:
    body = json.dumps(messages).encode()
    req = urllib.request.Request(
        _EXPO_URL, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        print(f"[push] Expo send failed: {exc!r}")
        return None


def send(title: str, body: str, data: dict | None = None,
         to: list[str] | None = None, sound: str = "default") -> dict:
    """Fan a push out to every registered device (or an explicit list).

    sound: 'default', or a bundled custom filename ('buy.wav' / 'sell.wav')."""
    targets = to if to is not None else tokens()
    if not targets:
        return {"sent": 0, "reason": "no registered devices"}
    messages = [{
        "to": tok,
        "title": title,
        "body": body,
        "sound": sound,
        "priority": "high",
        "data": data or {},
    } for tok in targets]
    resp = _post(messages)
    return {"sent": len(messages), "response": resp}


# iOS can't color the banner, so the TITLE carries the type at a glance:
# a typographic arrow + the advisor's verdict word (never emoji).
_ACTION_PREFIX = {
    "BUY":   "▲ BUY",       # ▲
    "ADD":   "▲ ADD",       # ▲
    "TRIM":  "▽ TRIM",      # ▽ (partial sell / take profit)
    "SELL":  "▼ SELL",      # ▼
    "AVOID": "▼ AVOID",     # ▼
    "HOLD":  "▬ HOLD",      # ▬
}


def send_signal(sig: dict) -> None:
    """Push one fired watchdog signal, titled by the advisor's verdict."""
    if not tokens():
        return
    side = sig.get("side", "buy")
    action = str(sig.get("action") or ("BUY" if side == "buy" else "SELL")).upper()

    # A runner ignition is its own beast — time-sensitive, potentially
    # explosive — so it gets a distinct urgent sound + title, set apart from a
    # routine (usually longer-term) buy or sell.
    if sig.get("rule") == "runner-ignition":
        prefix, sound = "▲▲ RUNNER", "runner.wav"
    elif sig.get("rule") == "plan-reeval":
        # A staged plan's premise changed — reconsider before you execute it.
        prefix = "◈ RECONSIDER"
        sound = "sell.wav" if action in ("SELL", "TRIM", "AVOID") else "buy.wav"
    else:
        prefix = _ACTION_PREFIX.get(action, ("▲ BUY" if side == "buy" else "▼ SELL"))
        sound = "buy.wav" if action in ("BUY", "ADD") else "sell.wav"

    title = f"{prefix} · {sig.get('symbol', '')}"  # e.g. "▲▲ RUNNER · SLBT"
    body = sig.get("headline") or sig.get("what") or "Watchdog signal fired"
    send(title, body, sound=sound, data={
        "type": "signal",
        "id": sig.get("id"),
        "symbol": sig.get("symbol"),
        "rule": sig.get("rule"),
        "side": side,
        "action": action,
    })
