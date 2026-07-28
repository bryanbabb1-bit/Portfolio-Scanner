"""Regression tests for the bug where the plan looked like it never saved.

Two causes, both covered here:
  1. A rebuild produced a fresh plan starting again at step 1 "sell
     immediately", discarding everything already executed.
  2. GET recomputed the expensive per-target price lookup on every page load,
     so a slow/failed load rendered as "no plan" and invited that rebuild.

    cd backend && .venv/Scripts/python -m pytest tests/test_transition_persistence.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"

import pytest  # noqa: E402

from app.services import advisor, transition as tr  # noqa: E402

from tests.test_transition import ANALYSIS, REPLY  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    monkeypatch.setattr(tr.settings, "ADVISOR_ENABLED", True)
    monkeypatch.setattr(tr, "analyse", lambda full=True: ANALYSIS)
    yield


def _stub(monkeypatch, reply=REPLY):
    seen = {}

    def fake(prompt, resume=None, research=False, model=None):
        seen["prompt"] = prompt
        return json.dumps(reply), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    return seen


# --------------------------------------------------- the execution ledger
def test_completed_moves_survive_a_rebuild(monkeypatch):
    """THE bug. Marking step 1 done then rebuilding must not resurrect it."""
    _stub(monkeypatch)
    tr.generate()
    tr.set_step_done(1)
    assert len(tr.completed_moves()) == 1

    tr.generate()                       # rebuild
    assert len(tr.completed_moves()) == 1, "the ledger was wiped by a rebuild"
    step1 = tr._load()["steps"][0]
    assert step1["done"] is True, "an executed move came back as outstanding"


def test_done_state_follows_the_move_not_the_step_number(monkeypatch):
    """A rebuild renumbers steps, so done-state is matched on move identity."""
    _stub(monkeypatch)
    tr.generate()
    tr.set_step_done(1)

    # Same two moves, returned in the opposite order with swapped numbers.
    swapped = {**REPLY, "steps": [
        {**REPLY["steps"][1], "n": 1},
        {**REPLY["steps"][0], "n": 2},
    ]}
    _stub(monkeypatch, swapped)
    tr.generate()

    by_sym = {s["sell_symbol"] or s["buy_symbol"]: s for s in tr._load()["steps"]}
    assert by_sym["MU"]["done"] is True      # the executed move, renumbered
    assert by_sym["LLY"]["done"] is False


def test_unmarking_a_step_removes_it_from_the_ledger(monkeypatch):
    _stub(monkeypatch)
    tr.generate()
    tr.set_step_done(1)
    tr.set_step_done(1, False)
    assert tr.completed_moves() == []
    tr.generate()
    assert tr._load()["steps"][0]["done"] is False


def test_executed_moves_are_fed_back_into_the_next_prompt(monkeypatch):
    """The action-ledger discipline: don't re-recommend what's already done."""
    seen = _stub(monkeypatch)
    tr.generate()
    tr.set_step_done(1)
    tr.generate()
    assert "ALREADY EXECUTED" in seen["prompt"]
    assert "Sell all $400 of MU" in seen["prompt"] or "MU" in seen["prompt"]


def test_activation_survives_a_rebuild(monkeypatch):
    """Targets stay on the watchlist and triggers stay live, so a rebuild must
    not silently report the plan as unmonitored."""
    _stub(monkeypatch)
    tr.generate()
    plan = tr._load()
    plan.update(activated=True, activated_at="2026-07-28 10:00:00",
                watched=["LLY"], watchpoints_created=2)
    tr._save(plan)

    tr.generate()
    after = tr._load()
    assert after["activated"] is True
    assert after["watched"] == ["LLY"]
    assert after["watchpoints_created"] == 2


# ------------------------------------------------------------ cheap reads
def test_cheap_analysis_skips_the_acquisition_target_lookups(monkeypatch):
    """full=False must not build a report per ACQUISITION TARGET.

    It still pays for portfolio_summary() — that is unavoidable for the gap,
    and it is the same warm, cached path every dashboard load already uses.
    The targets are the genuinely cold fetches: nothing else in the app
    touches them, so on a page load they were N uncached round trips, which is
    what pushed this endpoint past the tunnel's ceiling.
    """
    from app.services import transition as real

    monkeypatch.undo()                       # use the real analyse()
    held = {h["symbol"].upper()
            for h in real.pf_service.load_portfolio().get("holdings", [])}

    seen: list[str] = []
    orig = real.pf_service.build_report
    monkeypatch.setattr(real.pf_service, "build_report",
                        lambda sym, theme=None: (seen.append(sym.upper()),
                                                 orig(sym, theme))[1])

    real.analyse(full=False)
    target_lookups = [s for s in seen if s not in held]
    assert target_lookups == [], (
        f"cheap analysis still fetched {len(target_lookups)} uncached targets")


def test_full_analysis_does_price_the_targets(monkeypatch):
    """The counterpart: full=True must still produce levels to plan against,
    or the generator has nothing to anchor an entry on."""
    from app.services import transition as real

    monkeypatch.undo()
    a = real.analyse(full=True)
    if a["acquire"]:
        assert any(t["price"] for t in a["acquire"]), \
            "full analysis returned no prices for any target"
