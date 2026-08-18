"""The reclaim setup: beaten down, stopped falling, turning.

analyse() is tested directly with hand-built histories, because the shape of a
turn is the whole product here.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import reclaim as rc


def _hist(closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2025-06-02", periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": [500_000] * len(closes)},
                        index=idx)


def _wrecked_then_turning() -> list[float]:
    """100 -> 23 over a year, bases, then JUST reclaimed the 20-day.

    The turn is deliberately short. A long run above the 20-day is no longer a
    reclaim, it is an uptrend — and the screen is right to reject it.
    """
    fall = [100 - i * 0.55 for i in range(140)]        # down to ~23
    # Bottoms at 22, then works back to 26 — 22 is the PRIOR low.
    trough = [23.0, 22.4, 22.0, 22.6, 23.4, 24.0, 24.6, 25.2, 25.6, 26.0]
    base = [25.6 + (i % 4) * 0.2 for i in range(30)]
    # A shallower washout that HOLDS above 22 — the higher low — while still
    # dropping under the 20-day for several sessions.
    flush = [24.8, 24.0, 23.6, 23.4, 23.8]
    turn = [24.6, 25.6, 26.6, 27.4, 28.0]             # reclaims, on volume
    return fall + trough + base + flush + turn


def test_a_wrecked_name_that_turns_is_found():
    a = rc.analyse(_hist(_wrecked_then_turning()), 1.5)
    assert a is not None
    assert a["drawdown_pct"] >= rc.MIN_DRAWDOWN_PCT
    assert a["reclaim_score"] > 0


def test_a_name_at_its_highs_is_not_a_reclaim():
    # No damage to recover from — this is momentum, not a turn.
    assert rc.analyse(_hist([50 + i * 0.4 for i in range(200)]), 2.0) is None


def test_a_name_still_falling_is_rejected():
    # Below its 20-day, no turn. Catching this is the whole point.
    assert rc.analyse(_hist([100 - i * 0.45 for i in range(200)]), 2.0) is None


def test_a_name_that_already_ran_is_rejected():
    # Up 60%+ in 20 sessions: you would be the exit liquidity.
    closes = [100 - i * 0.5 for i in range(160)] + [20 + i * 1.6 for i in range(30)]
    assert rc.analyse(_hist(closes), 2.0) is None


def test_a_total_wreck_is_excluded():
    # Past ~92% down it is usually terminal rather than cheap.
    closes = [100 - i * 0.62 for i in range(150)] + [5.0] * 30 + [5 + i * 0.05 for i in range(20)]
    a = rc.analyse(_hist(closes), 1.5)
    assert a is None or a["drawdown_pct"] <= rc.MAX_DRAWDOWN_PCT


def test_a_higher_low_scores_above_a_lower_one():
    # The structural tell that separates "stopped falling" from "still falling".
    a = rc.analyse(_hist(_wrecked_then_turning()), 1.5)
    assert a["higher_low"] is True


def test_a_sideways_drifter_is_not_a_reclaim():
    """A name going nowhere ABOVE its 20-day clips it on noise every few days.

    Counting that as a reclaim scored a stale drifter 95.9 against 75.1 for a
    real turn — exactly backwards. A reclaim needs sustained time below and a
    cross with conviction.
    """
    drifter = _wrecked_then_turning() + [31 + (i % 3) * 0.1 for i in range(30)]
    assert rc.analyse(_hist(drifter), 1.5) is None


def test_participation_lifts_the_score():
    hist = _hist(_wrecked_then_turning())
    quiet = rc.analyse(hist, 1.2)
    loud = rc.analyse(hist, 3.0)
    assert loud["reclaim_score"] > quiet["reclaim_score"]


def test_too_little_history_is_not_guessed_at():
    assert rc.analyse(_hist([10.0] * 30), 2.0) is None
    assert rc.analyse(None, 2.0) is None


def test_it_does_not_require_a_volume_explosion():
    # The failure mode of the low-float screen: needing ignition means only ever
    # finding names already running.
    assert rc.MIN_RVOL < 2.0
    assert "AVOID" in rc.describe()["not_a_squeeze_screen"]
