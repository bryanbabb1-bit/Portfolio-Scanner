"""Standing instructions from the client. Not suggestions to the model.

WHY THIS EXISTS
---------------
Bryan told the advisor four separate times that he does not want SBUX, VXUS or
DE, and that he wants energy and high-growth names instead:

    2026-08-24 08:04  "I want energy stocks not retail ones like Starbucks or
                       target or that vanguard."
    2026-08-26 08:07  "The agent keeps recommending DE, SBux and Vxus - I don't
                       have interest in any of these"
    2026-08-26 08:08  "Energy, and high growth sectors."
    2026-08-26 10:32  "Stop recommmending SBUX or VXUS or Deere."

The advisor agreed every time — "dropping DE, SBUX and VXUS from your queue" —
and then the 09:42 brief, written ninety minutes after the third message, led
with "Buy $250 VXUS" and "Buy $200 SBUX" and described VXUS as "still my number
one, unchanged".

Nothing was broken in the way a crash is broken. The chat log recorded every
word, and the BRIEF never read it: `chat.recap_block()` was wired into the ask
path only, so a preference stated in conversation lived exactly as long as the
answer to that one question. The thing that issues orders had no idea.

TWO MECHANISMS, ON PURPOSE
--------------------------
1. The preferences are rendered into every prompt as a hard constraint.
2. The output is FILTERED against them afterwards.

The second is the one that matters. We have four recorded instances of the
model being told plainly and doing it anyway, so an instruction it can ignore
is not a constraint — it is a request. `filter_scout` and `filter_actions`
enforce what the prompt asks for, and log every removal so an ignored
instruction shows up as a number rather than as Bryan noticing again.
"""
from __future__ import annotations

import json
import re
import time

from ..config import settings

_FILE = settings.PORTFOLIO_FILE.parent / "preferences.json"

# A ticker inside a sentence of plain English. Deliberately conservative: 1-5
# capitals standing alone. Lowercase mentions ("Sbux") are handled by the
# caller passing an explicit symbol, not by widening this.
_TICKER = re.compile(r"\b([A-Z]{1,5})\b")

# Words that would otherwise scan as tickers in an action line.
_NOT_TICKERS = {
    "A", "I", "AI", "AN", "AND", "ARE", "AS", "AT", "BE", "BUT", "BUY", "BY",
    "CASH", "DO", "FOR", "GET", "HOLD", "IF", "IN", "IS", "IT", "ITS", "NEW",
    "NO", "NOT", "NOW", "OF", "OK", "ON", "ONE", "OR", "OUT", "PUT", "SELL",
    "SO", "THE", "TO", "TRIM", "UP", "US", "USD", "WAIT", "WHEN", "YOU", "YOUR",
    "ADD", "ALL", "ANY", "CAN", "EPS", "ETF", "FED", "GDP", "IPO", "NYSE", "P",
    "PE", "Q", "RSI", "SEC", "THAT", "THIS", "WILL", "WITH", "HIGH", "LOW",
}


def _read() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("blocked", [])
            d.setdefault("wanted", [])
            d.setdefault("notes", [])
            return d
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return {"blocked": [], "wanted": [], "notes": []}


def _write(d: dict) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[preferences] persist failed: {exc!r}")


def get() -> dict:
    return _read()


def blocked_symbols() -> set[str]:
    return {str(b.get("symbol", "")).upper() for b in _read().get("blocked", [])
            if b.get("symbol")}


def block(symbol: str, reason: str = "", source: str = "chat") -> dict:
    """Never recommend `symbol` again until the client says otherwise."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return _read()
    d = _read()
    rows = [b for b in d["blocked"] if str(b.get("symbol", "")).upper() != sym]
    rows.append({"symbol": sym, "reason": reason.strip(), "source": source,
                 "ts": time.time()})
    d["blocked"] = rows
    _write(d)
    print(f"[preferences] blocked {sym} ({reason or source})")
    return d


def unblock(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    d = _read()
    d["blocked"] = [b for b in d["blocked"]
                    if str(b.get("symbol", "")).upper() != sym]
    _write(d)
    return d


def want(theme: str, source: str = "chat") -> dict:
    """A sector or style the client wants ideas from."""
    t = (theme or "").strip()
    if not t:
        return _read()
    d = _read()
    if not any(w.get("theme", "").lower() == t.lower() for w in d["wanted"]):
        d["wanted"].append({"theme": t, "source": source, "ts": time.time()})
        _write(d)
        print(f"[preferences] wants {t}")
    return d


def unwant(theme: str) -> dict:
    d = _read()
    d["wanted"] = [w for w in d["wanted"]
                   if w.get("theme", "").lower() != (theme or "").lower()]
    _write(d)
    return d


def add_note(text: str, source: str = "chat") -> dict:
    t = (text or "").strip()
    if not t:
        return _read()
    d = _read()
    if not any(n.get("text", "").lower() == t.lower() for n in d["notes"]):
        d["notes"].append({"text": t, "source": source, "ts": time.time()})
        _write(d)
    return d


def drop_note(text: str) -> dict:
    d = _read()
    d["notes"] = [n for n in d["notes"]
                  if n.get("text", "").lower() != (text or "").lower()]
    _write(d)
    return d


# ------------------------------------------------------------------- prompts
def block_text() -> str:
    """The constraint paragraph injected into every advisor prompt."""
    d = _read()
    blocked, wanted, notes = d["blocked"], d["wanted"], d["notes"]
    if not (blocked or wanted or notes):
        return ""

    out = ["THE CLIENT'S STANDING PREFERENCES — these are INSTRUCTIONS, not "
           "context. He has had to repeat them; do not make him do it again."]
    if blocked:
        names = ", ".join(sorted({str(b["symbol"]).upper() for b in blocked}))
        out.append(
            f"  NEVER RECOMMEND: {names}. Do not put them in the plan, the "
            f"sequence, or the ideas list — not as a buy, not as a watch, not "
            f"as 'still my number one'. If he already owns one, you may discuss "
            f"holding or selling it, but never buying more. Anything you write "
            f"about these names as a purchase will be deleted before he sees "
            f"it, so spending the idea slot on one wastes it.")
    if wanted:
        themes = ", ".join(w["theme"] for w in wanted)
        out.append(
            f"  HE WANTS IDEAS FROM: {themes}. Bias every new idea here. If you "
            f"genuinely believe something outside these areas, you may say so, "
            f"but say plainly that it is outside what he asked for and why it "
            f"earns the exception.")
    for n in notes:
        out.append(f"  {n['text']}")
    return "\n".join(out) + "\n\n"


# ------------------------------------------------------------------ enforcing
def _tickers_in(text: str) -> set[str]:
    return {t for t in _TICKER.findall(text or "") if t not in _NOT_TICKERS}


_BUY_WORDS = ("buy", "add", "start", "open", "accumulate", "enter", "scale in")


def filter_scout(items: list) -> tuple[list, list[str]]:
    """Drop idea lines that name a blocked ticker. Returns (kept, removed)."""
    blocked = blocked_symbols()
    if not blocked or not items:
        return list(items or []), []
    kept, removed = [], []
    for item in items:
        text = item if isinstance(item, str) else json.dumps(item)
        hit = _tickers_in(text) & blocked
        (removed if hit else kept).append(item if not hit else f"{sorted(hit)[0]}")
    if removed:
        print(f"[preferences] dropped {len(removed)} idea(s) naming "
              f"{', '.join(sorted(set(removed)))} — the model was told not to")
    return kept, removed


def filter_actions(items: list) -> tuple[list, list[str]]:
    """Drop orders that BUY a blocked ticker.

    Sells and holds survive: he owns some of these, and refusing to discuss
    exiting a position he holds would be a different kind of unhelpful.
    """
    blocked = blocked_symbols()
    if not blocked or not items:
        return list(items or []), []
    kept, removed = [], []
    for item in items:
        text = (item if isinstance(item, str) else
                " ".join(str(v) for v in item.values()) if isinstance(item, dict)
                else str(item))
        low = text.lower()
        hit = _tickers_in(text) & blocked
        if hit and any(w in low for w in _BUY_WORDS):
            removed.append(sorted(hit)[0])
            continue
        kept.append(item)
    if removed:
        print(f"[preferences] dropped {len(removed)} buy order(s) for "
              f"{', '.join(sorted(set(removed)))} — blocked by the client")
    return kept, removed


def filter_candidates(candidates: list | None) -> list:
    """Strip blocked names from the discovery list BEFORE the model sees them.

    Cheaper than arguing with the output: an idea never shown is an idea never
    championed.
    """
    blocked = blocked_symbols()
    if not blocked or not candidates:
        return list(candidates or [])
    out = []
    for c in candidates:
        sym = (c.get("symbol") if isinstance(c, dict) else getattr(c, "symbol", ""))
        if str(sym or "").upper() in blocked:
            continue
        out.append(c)
    return out
