"""Learning-loop tests — verdict logic and the no-auto-apply guarantee.

    cd backend && .venv/Scripts/python -m pytest tests/test_learning.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import learning  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "_FILE", tmp_path / "rule_tuning.json")
    yield


def _bt(rule, signals=100, pf=1.5, avg=3.0, side="buy"):
    return {"rule": rule, "side": side, "signals": signals, "win_rate": 55.0,
            "avg_5": 1.0, "avg_20": avg, "avg_60": 4.0, "best": 20.0,
            "worst": -10.0, "profit_factor": pf, "avg_mae": -5.0, "symbols": 6}


def _live(rule, signals=10, avg=2.0):
    return {"rule": rule, "signals": signals, "win_rate": 60.0,
            "avg_effective_pct": avg, "best_pct": 9.0, "worst_pct": -4.0}


def _wire(monkeypatch, bt_rules, live_rules, has_report=True):
    monkeypatch.setattr(
        learning.bt, "last_result",
        lambda: {"rules": bt_rules, "as_of": "2026-01-01 00:00:00",
                 "period": {"start": "2021-01-01", "end": "2026-01-01"}}
        if has_report else None,
    )
    monkeypatch.setattr(
        learning.scorecard, "compute",
        lambda price_of=None: {"count": sum(r["signals"] for r in live_rules),
                               "overall_win_rate": 55.0, "overall_avg_pct": 1.0,
                               "rules": live_rules, "signals": []},
    )


# ------------------------------------------------------------------ verdicts
def test_strong_rule_is_earning(monkeypatch):
    _wire(monkeypatch, [_bt("good", pf=2.6, avg=4.2)], [])
    row = learning.rule_health()["rules"][0]
    assert row["verdict"] == "EARNING"
    assert row["proposal"] is None          # nothing to propose on a winner


def test_losing_rule_is_retired(monkeypatch):
    _wire(monkeypatch, [_bt("bad", pf=0.18, avg=-10.5, side="sell")], [])
    row = learning.rule_health()["rules"][0]
    assert row["verdict"] == "RETIRE"
    assert "Not yet validated" in row["proposal"]


def test_middling_rule_is_retuned(monkeypatch):
    _wire(monkeypatch, [_bt("meh", pf=0.85, avg=-1.2)], [])
    assert learning.rule_health()["rules"][0]["verdict"] == "RETUNE"


def test_barely_profitable_rule_is_marginal(monkeypatch):
    _wire(monkeypatch, [_bt("thin", pf=1.05, avg=0.3)], [])
    assert learning.rule_health()["rules"][0]["verdict"] == "MARGINAL"


def test_thin_backtest_sample_never_retires_a_rule(monkeypatch):
    """A rule that only fired 3 times historically must not be condemned on
    that evidence, however bad those three looked."""
    _wire(monkeypatch, [_bt("rare", signals=3, pf=0.1, avg=-20.0)], [])
    row = learning.rule_health()["rules"][0]
    assert row["verdict"] == "MARGINAL"
    assert "too thin" in row["reason"].lower()


def test_live_disagreement_is_surfaced_not_averaged(monkeypatch):
    """When live contradicts the replay the table must SAY so rather than
    silently blending two samples of very different size."""
    _wire(monkeypatch, [_bt("split", pf=2.0, avg=5.0)],
          [_live("split", signals=12, avg=-3.0)])
    row = learning.rule_health()["rules"][0]
    assert "DISAGREES" in row["reason"]


def test_tiny_live_sample_does_not_alter_the_reason(monkeypatch):
    _wire(monkeypatch, [_bt("x", pf=2.0, avg=5.0)], [_live("x", signals=2, avg=-9.0)])
    row = learning.rule_health()["rules"][0]
    assert "DISAGREES" not in row["reason"]
    assert row["live_signals"] == 2        # still reported, just not weighed


def test_no_backtest_yields_a_clear_note(monkeypatch):
    _wire(monkeypatch, [], [_live("a")], has_report=False)
    h = learning.rule_health()
    assert h["has_backtest"] is False
    assert any("no backtest" in n.lower() for n in h["notes"])


def test_worst_rules_sort_first(monkeypatch):
    _wire(monkeypatch, [
        _bt("fine", pf=2.0, avg=4.0),
        _bt("awful", pf=0.2, avg=-9.0),
        _bt("okay", pf=1.1, avg=0.4),
    ], [])
    assert [r["verdict"] for r in learning.rule_health()["rules"]] == [
        "RETIRE", "MARGINAL", "EARNING"
    ]


def test_regime_caveat_always_present(monkeypatch):
    _wire(monkeypatch, [_bt("g")], [])
    notes = learning.rule_health()["notes"]
    assert any("survivorship" in n.lower() for n in notes)


# ------------------------------------------------- the no-auto-apply contract
def test_accepting_a_proposal_changes_no_thresholds(monkeypatch):
    """The whole safety property: accepting records INTENT. It must not alter
    what fires — that stays a reviewed code change."""
    from app.services import conviction

    before = conviction._detect.__code__.co_consts
    _wire(monkeypatch, [_bt("sharp-breakdown", pf=0.18, avg=-10.5, side="sell")], [])

    learning.accept("sharp-breakdown", note="agreed, it sells bottoms")
    row = next(r for r in learning.rule_health()["rules"]
               if r["rule"] == "sharp-breakdown")

    assert row["accepted"]["note"] == "agreed, it sells bottoms"
    assert row["verdict"] == "RETIRE"       # verdict is unchanged by accepting
    assert conviction._detect.__code__.co_consts == before


def test_accept_round_trips_and_can_be_undone(monkeypatch):
    _wire(monkeypatch, [_bt("r", pf=0.5, avg=-3.0)], [])
    learning.accept("r", note="ok")
    assert learning.rule_health()["rules"][0]["accepted"] is not None
    assert learning.unaccept("r") is True
    assert learning.rule_health()["rules"][0]["accepted"] is None
    assert learning.unaccept("r") is False


# ------------------------------------------------------------- advisor feed
def test_facts_block_names_the_rules_that_failed(monkeypatch):
    _wire(monkeypatch, [
        _bt("oversold-at-support", pf=2.7, avg=4.2),
        _bt("sharp-breakdown", pf=0.18, avg=-10.5, side="sell"),
    ], [])
    block = learning.facts_block()
    assert "oversold-at-support" in block
    assert "sharp-breakdown" in block
    assert "NOT worked" in block


def test_facts_block_is_empty_without_a_backtest(monkeypatch):
    """No evidence means the advisor is told nothing, rather than being fed
    verdicts derived from a handful of live fires."""
    _wire(monkeypatch, [], [_live("a")], has_report=False)
    assert learning.facts_block() == ""
