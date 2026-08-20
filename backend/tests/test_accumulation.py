"""Unusual-volume screen — the leading signal that replaced the lagging one.

    cd backend && .venv/Scripts/python -m pytest tests/test_accumulation.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from app.services import accumulation as acc  # noqa: E402


def _hist(volumes, prices=None, n=100):
    """A history whose last bar carries the volume under test."""
    vols = [1_000_000] * (n - len(volumes)) + list(volumes)
    px = prices or [50.0] * n
    return pd.DataFrame({"Close": px, "Volume": vols})


def test_a_quiet_name_is_not_flagged():
    assert acc.analyse(_hist([1_100_000])) is None


def test_a_volume_explosion_is():
    a = acc.analyse(_hist([9_000_000]))
    assert a is not None and a["vol_ratio"] == 9.0
    assert a["loud"] is True


def test_the_surface_bar_sits_below_the_loud_bar():
    a = acc.analyse(_hist([6_000_000]))
    assert a is not None and a["loud"] is False     # shown, not shouted about


def test_the_baseline_excludes_the_last_week():
    """A name loud for five straight days must not normalise its own surge.

    If the trailing average includes the spike, sustained accumulation — the
    exact footprint being hunted — reads as ordinary within a week.
    """
    sustained = acc.analyse(_hist([8_000_000] * 5))
    assert sustained is not None
    assert sustained["vol_ratio"] == 8.0            # measured against the quiet
    assert sustained["week_ratio"] == 8.0


def test_an_illiquid_name_is_dropped_however_loud():
    # 20x average volume on a name that trades $30k a day is not accumulation.
    h = _hist([600_000])
    h["Volume"] = [30_000] * 99 + [600_000]
    h["Close"] = [0.5] * 100
    assert acc.analyse(h) is None


def test_a_sub_two_dollar_stock_is_dropped():
    h = _hist([9_000_000])
    h["Close"] = [1.20] * 100
    assert acc.analyse(h) is None


def test_a_short_history_cannot_be_judged():
    assert acc.analyse(_hist([9_000_000], n=40)) is None
    assert acc.analyse(None) is None


def test_the_beaten_down_flag_matches_the_measured_profile():
    """The median name that ran 50% was down 25% on the month beforehand."""
    prices = [100.0] * 80 + [70.0] * 20          # -30% over the last 20
    a = acc.analyse(_hist([9_000_000], prices=prices))
    assert a is not None
    assert a["drift_20d"] < -10 and a["beaten_down"] is True


def test_a_name_that_already_ran_is_flagged_but_not_as_beaten_down():
    prices = [50.0] * 80 + [90.0] * 20
    a = acc.analyse(_hist([9_000_000], prices=prices))
    assert a is not None and a["beaten_down"] is False


def test_results_are_ranked_loudest_first(monkeypatch):
    monkeypatch.setattr(acc.settings, "DATA_MODE", "live")
    monkeypatch.setattr(acc, "_batch_history", lambda syms: {
        "QUIET": _hist([6_000_000]),
        "LOUD": _hist([20_000_000]),
        "MID": _hist([9_000_000]),
    })
    out = acc.build(symbols=["QUIET", "LOUD", "MID"])
    assert [r["symbol"] for r in out["results"]] == ["LOUD", "MID", "QUIET"]


def test_the_measured_numbers_ship_with_the_results(monkeypatch):
    """The panel must never show a hit rate without its median beside it.

    13.7% of these touch +50% in a week and the median one is down 8%. A
    feature that reports only the first number is a lie by omission.
    """
    monkeypatch.setattr(acc.settings, "DATA_MODE", "live")
    monkeypatch.setattr(acc, "_batch_history", lambda syms: {})
    m = acc.build(symbols=[])["measured"]
    assert m["at_8x_touch_50"] == 13.7
    assert m["at_8x_median_5d"] < 0
    assert m["baseline_touch_50"] == 1.3
