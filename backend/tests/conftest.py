"""Suite-wide isolation from the user's real data files.

Tests run against the real app/data directory by default, and several of them
monkeypatch `load_portfolio` to return a stub book. `portfolio_summary()` then
runs the journal's snapshot diff against that stub, which read as "the client
closed every position" and wrote phantom sells — at mock prices — into the
REAL action journal. Repeated across runs that produced tens of thousands of
dollars of fictional realized losses and a -217% reported return.

Two earlier bugs had exactly this shape (the backtest report overwritten by a
stub run; the scorecard grading a delisted ticker against fallback mock data),
so the fix is applied once here for the whole suite rather than per file.

It is deliberately GENERIC: every module-level constant that points at a file
in the real data directory gets redirected to tmp_path, so a service added
later is covered without anyone remembering to update this list.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATA_MODE", "mock")

# Services that own persistent state. Import failures are tolerated so a
# broken optional module can never take the whole suite down at collection.
_SERVICE_MODULES = (
    "accumulation", "advisor", "backtest", "budget", "bigmoves", "catalysts", "chat", "cleansheet", "conviction",
    "journal", "learning", "pins", "plan", "preferences", "scorecard", "stance",
    "summary", "themes", "transition", "watchpoints",
)


@pytest.fixture(autouse=True)
def _isolate_user_ledgers(tmp_path_factory, monkeypatch):
    from app.config import settings

    real_dir = Path(settings.PORTFOLIO_FILE).parent.resolve()
    tmp = tmp_path_factory.mktemp("ledgers")

    for name in _SERVICE_MODULES:
        try:
            mod = __import__(f"app.services.{name}", fromlist=[name])
        except Exception:
            continue
        for attr in dir(mod):
            if not attr.startswith("_"):
                continue
            try:
                val = getattr(mod, attr)
            except Exception:
                continue
            if not isinstance(val, Path):
                continue
            try:
                inside = val.resolve().parent == real_dir
            except OSError:
                inside = False
            # portfolio.json itself is READ-only in tests and several of them
            # rely on the real book's shape, so leave it pointing at the source.
            if inside and val.name != Path(settings.PORTFOLIO_FILE).name:
                monkeypatch.setattr(mod, attr, tmp / f"{name}_{val.name}")
    yield
