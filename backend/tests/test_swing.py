"""The swing model: regime filter, no look-ahead, and cash-account discipline."""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import swing
from app.services.swing import SwingConfig


def _series(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"Open": closes, "High": [c * 1.01 for c in closes],
         "Low": [c * 0.99 for c in closes], "Close": closes,
         "Volume": [1_000_000] * len(closes)}, index=idx)


def _uptrend_with_dip() -> pd.DataFrame:
    # 260 rising bars so the 200-day exists and points up, then a sharp dip to
    # drive RSI under the threshold, then a turn back up.
    rising = [100 + i * 0.5 for i in range(260)]
    dip = [rising[-1] * f for f in (0.97, 0.94, 0.91, 0.89, 0.88)]
    turn = [dip[-1] * f for f in (1.02, 1.03, 1.05, 1.07, 1.09, 1.12, 1.15)]
    return _series(rising + dip + turn)


def test_a_pullback_inside_an_uptrend_is_taken():
    res = swing.simulate({"TEST": _uptrend_with_dip()}, SwingConfig())
    assert res.trades, "an oversold turn above the 200-day should trigger"
    assert "uptrend" in res.trades[0]["setup"]


def test_the_same_dip_below_the_200_day_is_rejected():
    # Identical shape, but the trend is DOWN. Buying oversold here is the
    # single most expensive mistake this filter exists to prevent.
    falling = [200 - i * 0.4 for i in range(260)]
    dip = [falling[-1] * f for f in (0.97, 0.94, 0.91, 0.89, 0.88)]
    turn = [dip[-1] * f for f in (1.02, 1.03, 1.05, 1.07)]
    res = swing.simulate({"TEST": _series(falling + dip + turn)}, SwingConfig())
    assert res.trades == []


def test_entry_fills_on_the_next_open_not_the_signal_close():
    df = _uptrend_with_dip()
    res = swing.simulate({"TEST": df}, SwingConfig())
    t = res.trades[0]
    entry_day = pd.Timestamp(t["entry_time"]).date()
    opens = {ts.date(): float(r["Open"]) for ts, r in df.iterrows()}
    # Priced off that day's OPEN (plus slippage), never a close it could not
    # have known at decision time.
    assert t["entry"] == pytest.approx(
        opens[entry_day] * (1 + SwingConfig().slippage_pct), rel=1e-6)


def test_a_falling_knife_is_not_caught():
    # Oversold and STILL falling: the rule wants the turn, not the fall.
    rising = [100 + i * 0.5 for i in range(260)]
    knife = [rising[-1] * (0.98 ** i) for i in range(1, 12)]
    res = swing.simulate({"TEST": _series(rising + knife)}, SwingConfig())
    assert res.trades == []


def test_position_never_exceeds_its_share_of_the_book():
    cfg = SwingConfig()
    res = swing.simulate({"TEST": _uptrend_with_dip()}, cfg)
    t = res.trades[0]
    assert t["shares"] * t["entry"] <= 1000.0 / cfg.max_open + 1e-6


def test_stop_is_below_entry_and_target_pays_the_configured_r():
    cfg = SwingConfig()
    t = swing.simulate({"TEST": _uptrend_with_dip()}, cfg).trades[0]
    assert t["stop"] < t["entry"] < t["target"]
    r = t["entry"] - t["stop"]
    assert t["target"] == pytest.approx(t["entry"] + cfg.target_r * r, rel=1e-6)


def test_everything_is_closed_out_by_the_end_of_the_test():
    # Otherwise ending equity is a mark, not cash, and the return is a guess.
    res = swing.simulate({"TEST": _uptrend_with_dip()}, SwingConfig())
    assert all(t["open_shares"] <= 1e-9 for t in res.trades)
    assert all(t["exit_reason"] for t in res.trades)


def test_empty_input_is_flat_not_a_crash():
    res = swing.simulate({}, SwingConfig())
    assert res.metrics["trades"] == 0
    assert res.metrics["ending_equity"] == 1000.0


def test_reports_hold_time_and_annualised_figures():
    res = swing.simulate({"TEST": _uptrend_with_dip()}, SwingConfig())
    assert set(res.extra) >= {"years", "cagr_pct", "avg_hold_days", "trades_per_year"}
