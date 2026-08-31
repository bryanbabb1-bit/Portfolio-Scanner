"""The pullback rule is the only edge here with a t-stat above 2, and it is
one condition away from being its opposite: buying weakness inside strength
works, buying weakness on its own is how accounts die. These tests pin the
three conditions and the two mistakes they exist to prevent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services import pullback, sleeve

CFG = dict(sleeve.DEFAULTS)


class _MD:
    """Minimal stand-in for a MarketData: history + source."""
    def __init__(self, hist, source="live"):
        self.history = hist
        self.source = source


def _frame(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({
        "Open": c.shift(1).fillna(c.iloc[0]),
        "High": c * 1.01,
        "Low": c * 0.99,
        "Close": c,
        "Volume": pd.Series(1_000_000.0, index=idx),
    })


def _uptrend_then(tail: list[float], base: int = 260, start: float = 100.0) -> pd.DataFrame:
    """A long grind higher (so the 200-day sits well below), then a tail."""
    rise = list(np.linspace(start, start * 1.9, base))
    return _frame(rise + tail)


# A long, shallow slide takes RSI under 35 while price stays well above the
# 200-day — that is what a pullback INSIDE an uptrend actually looks like. A
# violent drop would break the trend filter instead, which is a different
# (and correctly rejected) setup.
def _slide(start: float = 190.0, days: int = 16, step: float = 0.996) -> list[float]:
    out, p = [], start
    for _ in range(days):
        p *= step
        out.append(round(p, 2))
    return out


_DIP = _slide()
_TURN = _DIP + [round(_DIP[-1] * 1.015, 2)]


def test_a_pullback_in_an_uptrend_is_a_setup():
    row = pullback.evaluate("TEST", _MD(_uptrend_then(_TURN)), CFG)
    assert row is not None
    assert row["rsi_prev"] < pullback.RSI_ENTRY < 100
    assert row["rsi"] > row["rsi_prev"]
    assert row["stop"] < row["entry"]
    assert row["pct_above_200d"] > 0
    # The stop is volatility-based, not a fixed percentage.
    assert row["entry"] - row["stop"] == pytest.approx(CFG["pullback_atr_stop"] * row["atr"], rel=0.02)


def test_a_falling_knife_is_not_caught():
    """Same dip, no turn — RSI still falling on the last bar."""
    assert pullback.evaluate("TEST", _MD(_uptrend_then(_DIP)), CFG) is None


def test_the_same_dip_below_the_200_day_is_rejected():
    """The regime filter is the whole rule. A long decline puts price under
    its 200-day, and then an oversold turn is not a buy."""
    fall = list(np.linspace(200.0, 90.0, 260))
    hist = _frame(fall + _slide(start=90.0) + [82.0])
    assert pullback.evaluate("TEST", _MD(hist), CFG) is None


def test_a_shallow_wobble_is_not_oversold_enough():
    mild = [189, 188.4, 188.0, 187.6, 188.2]
    assert pullback.evaluate("TEST", _MD(_uptrend_then(mild)), CFG) is None


def test_mock_data_never_produces_a_setup():
    assert pullback.evaluate("TEST", _MD(_uptrend_then(_TURN), source="mock"), CFG) is None


def test_blocked_names_are_dropped_from_the_universe(monkeypatch):
    monkeypatch.setattr(pullback, "_preferences_block", lambda: {"NVDA", "SPY"})
    monkeypatch.setattr(
        "app.services.portfolio.load_portfolio",
        lambda: {"holdings": [{"symbol": "NVDA"}], "watchlist": [{"symbol": "SOUN"}]})
    syms = pullback._universe()
    assert "NVDA" not in syms and "SPY" not in syms
    assert "SOUN" in syms


def test_pullback_tickets_carry_the_reason_and_a_real_stop(monkeypatch):
    book = sleeve._empty()
    rows = [pullback.evaluate("TEST", _MD(_uptrend_then(_TURN)), CFG)]
    issued = sleeve.from_pullback(rows, book=book, eq=1500, push_it=False)
    assert len(issued) == 1
    t = issued[0]
    assert t["engine"] == "pullback" and t["status"] == "armed"
    assert any("200-day" in w for w in t["why"])
    assert t["stop"] < t["entry"] < t["target"]
    assert t["risk_usd"] <= 75 + 0.01           # 5% of 1500
