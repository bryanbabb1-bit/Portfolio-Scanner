"""Grading the desk's calls.

The scoring has to be able to say the desk was WRONG, or it is decoration.
"""
from __future__ import annotations

import time

import pytest

from app.services import verdict_score as vs


def test_a_skip_is_right_when_the_name_does_not_run():
    g = vs.grade_one("AVOID", 10.0, 10.4)      # +4%
    assert g["graded"] and g["right"] is True


def test_a_skip_is_wrong_when_the_name_runs_away():
    # This is the failure mode the whole scorecard exists to catch.
    g = vs.grade_one("AVOID", 10.0, 14.0)      # +40%
    assert g["graded"] and g["right"] is False
    assert "ran +40%" in g["note"]


def test_a_skip_on_a_faller_is_right():
    g = vs.grade_one("SELL", 10.0, 6.0)
    assert g["right"] is True


def test_a_buy_is_only_right_if_it_actually_moved():
    assert vs.grade_one("BUY", 10.0, 11.5)["right"] is True    # +15%
    assert vs.grade_one("BUY", 10.0, 10.3)["right"] is False   # +3%, no move


def test_hold_makes_no_claim_and_is_not_graded():
    # Grading a HOLD would let the desk bank credit for saying nothing.
    for action in ("HOLD", "WATCH", ""):
        g = vs.grade_one(action, 10.0, 20.0)
        assert g["graded"] is False and g["right"] is None


def test_a_rejected_watch_is_a_skip_and_gets_graded():
    """The hole this scorecard nearly fell through.

    When the screen changed the judge started writing WATCH instead of AVOID
    while its verdict stayed REJECT — "watch above $8.39, don't buy here". That
    is a skip call, and grading it as neutral meant a screen that rejected
    everything could never be scored wrong.
    """
    g = vs.grade_one("WATCH", 10.0, 14.0, "REJECT")     # told to skip, ran +40%
    assert g["graded"] is True and g["right"] is False
    assert g["graded_as"] == "AVOID"

    g = vs.grade_one("WATCH", 10.0, 10.2, "REJECT")     # told to skip, went flat
    assert g["graded"] is True and g["right"] is True


def test_an_approved_watch_is_a_real_conditional_and_stays_ungraded():
    # "APPROVE — buy only above $16" makes no claim about what happens next.
    g = vs.grade_one("WATCH", 10.0, 14.0, "APPROVE")
    assert g["graded"] is False and g["right"] is None


def test_the_threshold_is_asymmetric_on_purpose():
    # Skipping something that rose 2% was not a bad call.
    assert vs.grade_one("AVOID", 10.0, 10.2)["right"] is True
    assert vs.MOVE_PCT == 10.0


def _debate(sym, ts, price, action):
    return {"symbol": sym, "ts": ts, "price": price, "action": action,
            "verdict": "REJECT", "headline": "h"}


def test_a_call_still_in_flight_is_not_scored(monkeypatch):
    from app.services import debate
    monkeypatch.setattr(debate, "history",
                        lambda limit=200: [_debate("AAA", time.time() - 86400,
                                                   10.0, "AVOID")])
    out = vs.scorecard()
    assert out["pending"] == 1
    assert out["graded"] == 0
    # A call one day old is not a call that was wrong.
    assert out["rows"][0]["right"] is None


def test_a_ripe_call_is_graded(monkeypatch):
    from app.services import debate
    monkeypatch.setattr(debate, "history",
                        lambda limit=200: [_debate("AAA", time.time() - 8 * 86400,
                                                   10.0, "AVOID")])
    monkeypatch.setattr(vs, "_price_now", lambda s: (20.0, "live"))
    out = vs.scorecard()
    assert out["graded"] == 1
    assert out["hit_rate"] == 0.0            # skipped a name that doubled
    assert out["by_action"]["AVOID"]["hit_rate"] == 0.0


def test_hit_rate_is_reported_with_its_sample_size(monkeypatch):
    from app.services import debate
    monkeypatch.setattr(debate, "history", lambda limit=200: [
        _debate(f"S{i}", time.time() - 8 * 86400, 10.0, "AVOID") for i in range(3)])
    monkeypatch.setattr(vs, "_price_now", lambda s: (10.1, "live"))
    out = vs.scorecard()
    assert out["hit_rate"] == 100.0
    # ...and says plainly that three calls prove nothing.
    assert "too few" in out["confidence"]


def test_a_missing_price_is_not_counted_as_a_win(monkeypatch):
    from app.services import debate
    monkeypatch.setattr(debate, "history",
                        lambda limit=200: [_debate("AAA", time.time() - 8 * 86400,
                                                   10.0, "AVOID")])
    monkeypatch.setattr(vs, "_price_now", lambda s: (None, "mock"))
    out = vs.scorecard()
    assert out["graded"] == 0
    assert out["hit_rate"] is None
