"""The daily CLI ceiling that stops a background loop eating the subscription.

    cd backend && .venv/Scripts/python -m pytest tests/test_budget.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import budget as b  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "_FILE", tmp_path / "cli_budget.json")
    monkeypatch.setattr(b, "LIMITS", {"user": 0, "brief": 4, "desk": 12, "signal": 3})
    yield


def test_a_tier_spends_down_to_its_cap():
    assert [b.take("signal") for _ in range(3)] == [True, True, True]
    assert b.take("signal") is False


def test_the_users_own_questions_are_never_rationed():
    """A zero limit means unlimited on purpose. Running out of quota because
    background enrichment ate it is the failure this file exists to prevent;
    refusing to answer him would be the same failure wearing a different hat."""
    assert all(b.take("user") for _ in range(500))
    assert b.remaining("user") is None


def test_tiers_do_not_borrow_from_each_other():
    for _ in range(3):
        b.take("signal")
    assert b.take("signal") is False
    assert b.take("brief") is True          # the brief still has its own room
    assert b.take("desk", 6) is True


def test_a_multi_call_claim_is_all_or_nothing():
    """A debate is six calls. Letting it start with three left would spend the
    remainder and still produce nothing usable."""
    assert b.take("desk", 6) is True
    assert b.take("desk", 6) is True        # 12 of 12
    assert b.take("desk", 6) is False
    assert b.remaining("desk") == 0


def test_a_partial_claim_does_not_consume_the_remainder():
    b.take("desk", 10)                      # 10 of 12
    assert b.take("desk", 6) is False       # would overshoot, so refused
    assert b.remaining("desk") == 2         # ...and the 2 are still there
    assert b.take("desk", 2) is True


def test_a_new_day_starts_clean(monkeypatch):
    for _ in range(3):
        b.take("signal")
    assert b.take("signal") is False
    monkeypatch.setattr(b, "_today", lambda: "2099-01-01")
    assert b.take("signal") is True


def test_blocked_attempts_are_counted_so_quiet_days_are_explainable():
    for _ in range(3):
        b.take("signal")
    b.take("signal")
    b.take("signal")
    st = b.state()
    assert st["spent"]["signal"] == 3
    assert st["blocked"]["signal"] == 2     # "why did nothing get written up"
    assert st["remaining"]["signal"] == 0
    assert st["remaining"]["user"] is None


def test_an_unknown_tier_is_treated_as_unlimited_not_blocked():
    # A new caller must never be silently muted by forgetting to add a limit.
    assert b.take("something_new") is True
