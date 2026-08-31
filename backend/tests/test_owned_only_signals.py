"""Signals fire only for names the client owns or watches.

    cd backend && .venv/Scripts/python -m pytest tests/test_owned_only_signals.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import conviction  # noqa: E402


# ------------------------------------------------------- owned-only signals
@pytest.fixture
def no_side_effects(monkeypatch, tmp_path):
    monkeypatch.setattr(conviction, "_FIRED_FILE", tmp_path / "fired.json")
    monkeypatch.setattr(conviction, "_NOTES_FILE", tmp_path / "notes.json")
    monkeypatch.setattr(conviction, "market_active", lambda: True)
    yield


def _run_scan(monkeypatch, owned_only: bool):
    """Run a scan, recording whether the whole-market scanners were consulted."""
    from app.services import discovery, runner
    from app.services import portfolio as pf_service

    cfg = {"holdings": [{"symbol": "NVDA", "shares": 1, "cost_basis": 100}],
           "watchlist": [], "signals_owned_only": owned_only,
           "quiet_unowned_low_cash": False, "cash": 50_000}
    monkeypatch.setattr(pf_service, "load_portfolio", lambda: cfg)

    touched = {"discovery": 0, "runner": 0}
    monkeypatch.setattr(
        discovery, "discover",
        lambda **kw: touched.__setitem__("discovery", touched["discovery"] + 1)
        or {"results": [], "count": 0, "universe": 0, "source": "mock"})
    monkeypatch.setattr(
        runner, "igniting_movers",
        lambda *a, **k: touched.__setitem__("runner", touched["runner"] + 1) or [])

    conviction.scan()
    return touched


def test_owned_only_skips_the_whole_market_scanners(monkeypatch, no_side_effects):
    """A slap on a name outside the book is an alert you cannot act on, and
    since the discovery universe went market-wide it would be constant."""
    touched = _run_scan(monkeypatch, owned_only=True)
    assert touched["discovery"] == 0
    assert touched["runner"] == 0


def test_disabling_it_restores_the_market_wide_scan(monkeypatch, no_side_effects):
    from app.services import sleeve
    monkeypatch.setattr(sleeve, "enabled", lambda: False)
    touched = _run_scan(monkeypatch, owned_only=False)
    assert touched["discovery"] == 1
    assert touched["runner"] == 1


def test_the_sleeve_owns_runners_when_it_is_on(monkeypatch, no_side_effects):
    """With the trading sleeve enabled the core scan never issues runner
    warnings — the sleeve issues sized tickets with exits instead, and two
    alerts for one name would be worse than either alone."""
    from app.services import sleeve
    monkeypatch.setattr(sleeve, "enabled", lambda: True)
    touched = _run_scan(monkeypatch, owned_only=False)
    assert touched["discovery"] == 1
    assert touched["runner"] == 0


def test_default_is_owned_only(monkeypatch, no_side_effects):
    """Config silent -> quiet. The noisy behaviour must be opt-in."""
    from app.services import discovery, runner
    from app.services import portfolio as pf_service

    monkeypatch.setattr(pf_service, "load_portfolio",
                        lambda: {"holdings": [], "watchlist": [], "cash": 50_000})
    seen = []
    monkeypatch.setattr(discovery, "discover",
                        lambda **kw: seen.append(1) or {"results": []})
    monkeypatch.setattr(runner, "igniting_movers", lambda *a, **k: seen.append(1) or [])
    conviction.scan()
    assert seen == []


def test_a_config_read_failure_falls_back_to_quiet(monkeypatch, no_side_effects):
    """owned_only is read outside the try that computes cash, so a config
    failure can never leave it undefined, and must fail quiet, not loud."""
    from app.services import discovery, runner
    from app.services import portfolio as pf_service

    def boom():
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(pf_service, "load_portfolio", boom)
    seen = []
    monkeypatch.setattr(discovery, "discover",
                        lambda **kw: seen.append(1) or {"results": []})
    monkeypatch.setattr(runner, "igniting_movers", lambda *a, **k: seen.append(1) or [])
    conviction.scan()          # must not raise
    assert seen == []

