"""Owned-only signals + the advisor/transition consistency link.

    cd backend && .venv/Scripts/python -m pytest tests/test_owned_only_signals.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import conviction, transition as tr  # noqa: E402


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
    """A slap on a name outside the book is an alert you cannot act on — and
    since the discovery universe went market-wide it would be constant."""
    touched = _run_scan(monkeypatch, owned_only=True)
    assert touched["discovery"] == 0
    assert touched["runner"] == 0


def test_disabling_it_restores_the_market_wide_scan(monkeypatch, no_side_effects):
    touched = _run_scan(monkeypatch, owned_only=False)
    assert touched["discovery"] == 1
    assert touched["runner"] == 1


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
    failure can never leave it undefined — and must fail quiet, not loud."""
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


# ------------------------------------- advisor <-> transition consistency
def test_a_draft_plan_still_reaches_the_advisor(monkeypatch, tmp_path):
    """THE bug behind "the brief and the plan disagree": facts_block was gated
    on activation, so a generated-but-not-activated plan was invisible to the
    brief and the two surfaces issued conflicting orders."""
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    tr._save({
        "headline": "Stage out of chips.",
        "activated": False,
        "steps": [{"n": 1, "trigger": "immediately", "sell": "Sell $400 of MU.",
                   "buy": "", "why": "", "realizes": "", "done": False}],
        "completed": [],
    })
    block = tr.facts_block()
    assert block, "a draft plan must still be visible to the advisor"
    assert "DRAFT" in block
    assert "MU" in block
    assert "CONSISTENT" in block


def test_activation_is_labelled_when_active(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    tr._save({"activated": True, "completed": [],
              "steps": [{"n": 1, "trigger": "now", "sell": "Sell MU.",
                         "buy": "", "why": "", "realizes": "", "done": False}]})
    assert "[ACTIVE]" in tr.facts_block()


def test_executed_steps_are_shown_as_done_not_outstanding(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    tr._save({
        "activated": True,
        "steps": [{"n": 1, "trigger": "now", "sell": "Sell $400 of MU.",
                   "buy": "", "why": "", "realizes": "", "done": True}],
        "completed": [{"sig": "MU||Sell $400 of MU.|", "sell": "Sell $400 of MU.",
                       "buy": "", "done_at": "2026-07-28 10:00:00"}],
    })
    block = tr.facts_block()
    assert "ALREADY DONE" in block
    assert "OUTSTANDING" not in block


def test_no_plan_means_no_block(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    assert tr.facts_block() == ""


def test_book_context_carries_the_plan(monkeypatch, tmp_path):
    """_book_context feeds the stock review, chat and notification advice —
    injecting there is what stops each surface freelancing."""
    from app.services import advisor

    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    tr._save({"activated": True, "completed": [], "headline": "Stage out of chips.",
              "steps": [{"n": 1, "trigger": "now", "sell": "Sell $400 of MU.",
                         "buy": "", "why": "", "realizes": "", "done": False}]})
    ctx = advisor._book_context()
    assert "TRANSITION PLAN" in ctx
