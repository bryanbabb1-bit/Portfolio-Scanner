"""Automatic theme categorization by ticker.

Nobody should have to hand-pick "AI Infrastructure" for NVDA. Resolution
order, cheapest first:
  1. built-in seed map (Discovery universe + known holdings — zero cost)
  2. persistent learned cache (data/theme_map.json)
  3. one standard-tier Claude call for a genuinely new ticker — the result
     is cached forever, so each unknown symbol costs one tiny call, once.
A manual theme on a holding/watch item still wins as an override.
"""
from __future__ import annotations

import json
import threading

from ..config import settings
from . import discovery

_MAP_FILE = settings.PORTFOLIO_FILE.parent / "theme_map.json"
_lock = threading.Lock()

# Held / historical names that aren't in the Discovery universe.
_EXTRA: dict[str, str] = {
    "NVDA": "AI Infrastructure", "AMD": "AI Infrastructure",
    "AVGO": "AI Infrastructure", "TSM": "AI Infrastructure",
    "MU": "AI Infrastructure", "NBIS": "AI Infrastructure",
    "MSFT": "AI", "META": "AI", "NOW": "AI", "PLTR": "AI",
    "IREN": "Compute Power", "CIFR": "Compute Power",
    "WULF": "Compute Power", "CLSK": "Compute Power",
    "AMZN": "Tech", "MELI": "Tech", "GRAB": "Tech", "ONDS": "Tech",
    "SGOV": "Cash & Income", "BIL": "Cash & Income", "SPY": "Tech",
}


def _seed() -> dict[str, str]:
    seed = dict(_EXTRA)
    for theme, rows in discovery.UNIVERSE.items():
        for sym, _name in rows:
            seed.setdefault(sym, theme)
    return seed


_SEED = _seed()


def _load_learned() -> dict[str, str]:
    try:
        with open(_MAP_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_learned: dict[str, str] = _load_learned()


def _classify_with_claude(symbol: str) -> str | None:
    """One-time, cached-forever categorization of an unknown ticker."""
    from . import advisor
    from . import portfolio as pf_service

    try:
        themes = pf_service.load_portfolio().get("themes", {})
    except Exception:
        themes = {}
    if not themes:
        return None
    menu = "\n".join(f"- {name}: {desc}" for name, desc in themes.items())
    prompt = (
        f"Categorize the stock ticker {symbol} into exactly one of these "
        f"investment themes:\n{menu}\n\n"
        f"Reply with ONLY the theme name, nothing else."
    )
    raw, _ = advisor._run_claude(prompt, model=settings.CLAUDE_MODEL_STANDARD)
    if not raw:
        return None
    answer = raw.strip().strip('"').strip()
    # Accept only an exact (case-insensitive) match against the defined themes.
    for name in themes:
        if answer.lower() == name.lower():
            return name
    return None


def theme_for(symbol: str) -> str:
    sym = symbol.upper().strip()
    if sym in _SEED:
        return _SEED[sym]
    if sym in _learned:
        return _learned[sym]
    theme = _classify_with_claude(sym) if settings.ADVISOR_ENABLED else None
    if theme is None:
        return "Other"  # not persisted — retry when the advisor is available
    with _lock:
        _learned[sym] = theme
        try:
            _MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_MAP_FILE, "w") as f:
                json.dump(_learned, f, indent=2, sort_keys=True)
        except OSError as exc:
            print(f"[themes] persist failed: {exc!r}")
    return theme


def resolve(symbol: str, manual: str | None) -> str:
    """Manual selection wins; otherwise auto-categorize."""
    return manual if manual else theme_for(symbol)
