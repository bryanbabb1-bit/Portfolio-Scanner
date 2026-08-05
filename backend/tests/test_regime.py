"""The regime switch: hold the index while it rises, hunt when it doesn't."""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import regime
from app.services.regime import RegimeConfig


def _frame(closes: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"Open": closes, "High": [c * 1.01 for c in closes],
         "Low": [c * 0.99 for c in closes], "Close": closes,
         "Volume": [1_000_000] * len(closes)}, index=idx)


def test_regime_needs_consecutive_closes_to_flip():
    cfg = RegimeConfig(confirm_days=3)
    # 260 rising bars establishes an uptrend well clear of the 200-day.
    df = _frame([100 + i * 0.5 for i in range(260)])
    series = regime.regime_series(df, cfg)
    assert series[df.index[-1].date()] is True
    # Before the 200-day exists there is no regime to be in.
    assert series[df.index[10].date()] is False


def test_risk_on_holds_the_index():
    rising = _frame([100 + i * 0.5 for i in range(300)])
    res = regime.simulate({"SPY": rising}, RegimeConfig())
    assert res.trades, "a rising index should be held"
    assert res.trades[0]["symbol"] == "SPY"
    assert "risk-on" in res.trades[0]["setup"]
    assert res.extra["pct_risk_on"] > 0


def test_the_index_is_sold_when_the_regime_turns_off():
    rising = [100 + i * 0.5 for i in range(280)]
    falling = [rising[-1] * (0.985 ** i) for i in range(1, 90)]
    res = regime.simulate({"SPY": _frame(rising + falling)}, RegimeConfig())
    spy_trades = [t for t in res.trades if t["symbol"] == "SPY"]
    assert spy_trades
    assert spy_trades[0]["exit_reason"], "the index position must be closed out"


def test_no_index_history_is_an_explicit_error():
    # Silently simulating without a regime would produce a number that looks
    # like a result and isn't one.
    with pytest.raises(ValueError):
        regime.simulate({"AAPL": _frame([100.0] * 300)}, RegimeConfig())


def test_hunting_can_be_ablated():
    # The switch exists so "does the hunting earn its place" is answerable by
    # running it, not by arguing about it.
    rising = [100 + i * 0.5 for i in range(280)]
    falling = [rising[-1] * (0.99 ** i) for i in range(1, 120)]
    frames = {"SPY": _frame(rising + falling),
              "AAA": _frame(rising + falling)}
    on = regime.simulate(frames, RegimeConfig(hunt_in_risk_off=True))
    off = regime.simulate(frames, RegimeConfig(hunt_in_risk_off=False))
    assert len([t for t in off.trades if t["symbol"] != "SPY"]) == 0
    assert len(on.trades) >= len(off.trades)


def test_everything_is_flat_at_the_end():
    rising = _frame([100 + i * 0.5 for i in range(300)])
    res = regime.simulate({"SPY": rising}, RegimeConfig())
    assert all(t["open_shares"] <= 1e-9 for t in res.trades)


def test_reports_the_share_of_time_spent_risk_on():
    rising = _frame([100 + i * 0.5 for i in range(300)])
    res = regime.simulate({"SPY": rising}, RegimeConfig())
    assert 0 <= res.extra["pct_risk_on"] <= 100
    assert set(res.extra) >= {"years", "cagr_pct", "pct_risk_on",
                              "index_trades", "hunt_trades"}
