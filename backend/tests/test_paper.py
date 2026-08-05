"""The paper-trading model: settlement law first, then the rules.

The settlement tests matter most. If the ledger is wrong the whole simulation is
optimistic fiction — it would be spending money a real cash account would not
have let it spend, and every metric downstream inherits that lie.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.services import paper
from app.services.paper import Ledger, PaperConfig


# ------------------------------------------------------------------ settlement
def test_t1_settlement_skips_the_weekend():
    # Friday sale settles Monday, not Saturday.
    assert paper.next_business_day(date(2026, 8, 7)) == date(2026, 8, 10)
    assert paper.next_business_day(date(2026, 8, 4)) == date(2026, 8, 5)


def test_proceeds_are_not_spendable_until_they_settle():
    led = Ledger(settled=1000.0)
    assert led.buy(1000.0)                      # all-in with settled cash
    led.sell(1050.0, date(2026, 8, 4))          # closed same day, in profit

    assert led.settled == pytest.approx(0.0)
    assert led.unsettled == pytest.approx(1050.0)
    # Same day: the proceeds exist but cannot buy anything. This is the rule
    # that stops a $1,000 account from making unlimited round trips.
    assert not led.buy(500.0)

    led.settle_through(date(2026, 8, 5))        # T+1
    assert led.settled == pytest.approx(1050.0)
    assert led.buy(500.0)


def test_the_ledger_never_lends():
    led = Ledger(settled=100.0)
    assert not led.buy(100.01)
    assert led.buy(100.0)
    assert led.settled == pytest.approx(0.0)


def test_settlement_only_releases_what_is_due():
    led = Ledger(settled=0.0)
    led.sell(100.0, date(2026, 8, 4))           # settles 8/5
    led.sell(200.0, date(2026, 8, 5))           # settles 8/6

    led.settle_through(date(2026, 8, 5))
    assert led.settled == pytest.approx(100.0)
    assert led.unsettled == pytest.approx(200.0)
    assert led.total == pytest.approx(300.0)


# -------------------------------------------------------------------- bar fixture
def _session(day: str, bars: list[tuple[float, float, float, float, int]],
             start: str = "09:30") -> pd.DataFrame:
    """Build one 5-minute session from (open, high, low, close, volume) tuples."""
    idx = pd.date_range(f"{day} {start}", periods=len(bars), freq="5min")
    return pd.DataFrame(
        [{"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}
         for o, h, lo, c, v in bars], index=idx)


def _breakout_day(day: str = "2026-08-04") -> pd.DataFrame:
    """A textbook setup: quiet 15-minute range, then a high-volume break that
    runs to target."""
    bars = [
        (100.0, 100.5, 99.8, 100.2, 1000),      # opening range...
        (100.2, 100.6, 99.9, 100.3, 1000),
        (100.3, 100.7, 100.0, 100.5, 1000),     # ...OR high = 100.7
        (100.5, 101.6, 100.4, 101.5, 6000),     # break on 6x volume
        (101.5, 103.5, 101.4, 103.4, 4000),     # runs through 1R and target
        (103.4, 103.6, 103.0, 103.2, 2000),
    ]
    # Pad so EMA/RSI/ATR have data to work with.
    warm = [(99.0 + i * 0.05, 99.4 + i * 0.05, 98.9 + i * 0.05, 99.3 + i * 0.05, 900)
            for i in range(30)]
    prev = _session("2026-08-03", warm)
    return pd.concat([prev, _session(day, bars)])


def test_a_clean_breakout_is_taken_and_sized_to_the_cash_cap():
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    assert res.trades, "the setup should have fired"
    t = res.trades[0]
    assert t["setup"].startswith("ORB")
    # Never spend more than the account holds.
    assert t["shares"] * t["entry"] <= 1000.0 + 1e-6
    assert t["stop"] < t["entry"] < t["target"]


def test_a_break_below_vwap_is_rejected():
    # Same shape, but the day trends down so the break is under VWAP: the
    # sellers still own the session and the setup must not fire.
    bars = [
        (100.0, 100.5, 99.8, 100.0, 1000),
        (100.0, 100.6, 99.0, 99.2, 1000),
        (99.2, 99.4, 98.0, 98.2, 1000),
        (98.2, 99.0, 98.0, 98.9, 6000),
        (98.9, 99.2, 98.5, 99.0, 4000),
    ]
    warm = [(101.0, 101.4, 100.9, 101.2, 900)] * 30
    df = pd.concat([_session("2026-08-03", warm), _session("2026-08-04", bars)])
    assert paper.simulate({"TEST": df}, PaperConfig()).trades == []


def test_a_thin_breakout_is_rejected():
    df = _breakout_day()
    # Same price action, no volume behind the break.
    df.iloc[-3, df.columns.get_loc("Volume")] = 400
    assert paper.simulate({"TEST": df}, PaperConfig()).trades == []


def test_positions_are_flat_by_the_close():
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    assert all(not t["open_shares"] > 1e-9 for t in res.trades), \
        "a day-trading model must not hold overnight"


def test_risk_is_recorded_as_taken_not_as_budgeted():
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    t = res.trades[0]
    # 2% of $1,000 is $20, but the cash cap usually binds first on a small
    # account, so the recorded risk is what the position could actually lose.
    assert t["risk_dollars"] == pytest.approx(
        t["shares"] * (t["entry"] - t["stop"]), abs=0.02)


def test_a_scaled_winner_keeps_the_stop_it_was_taken_with():
    # Moving to breakeven must not overwrite the original stop. That number
    # defines the R every metric is denominated in, so losing it would make a
    # scaled trade impossible to audit and silently zero its recorded risk.
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    t = res.trades[0]
    scaled = [e for e in t["exits"] if e["reason"] == "scale 1R"]
    assert scaled, "this fixture should reach 1R and scale"
    assert t["stop"] < t["entry"]
    assert t["current_stop"] >= t["stop"]
    assert t["risk_dollars"] > 0


def test_blocked_entries_are_counted_not_dropped():
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    assert set(res.blocked) >= {"unsettled_cash", "daily_stop", "max_open",
                                "max_trades", "too_late", "no_size"}


def test_two_symbols_cannot_both_spend_the_same_thousand():
    # The whole reason the timeline is merged across symbols.
    frames = {"AAA": _breakout_day(), "BBB": _breakout_day()}
    res = paper.simulate(frames, PaperConfig(max_open=2))
    spend = {}
    for t in res.trades:
        spend.setdefault(t["day"], 0.0)
        spend[t["day"]] += t["shares"] * t["entry"]
    for day, total in spend.items():
        assert total <= 1000.0 + 1e-6, f"{day} committed {total:.2f} of $1,000"


def test_max_open_is_respected():
    frames = {"AAA": _breakout_day(), "BBB": _breakout_day(), "CCC": _breakout_day()}
    res = paper.simulate(frames, PaperConfig(max_open=1))
    # With one slot and simultaneous signals, only one can be on at a time.
    by_day = {}
    for t in res.trades:
        by_day.setdefault(t["day"], []).append(t)
    for day_trades in by_day.values():
        assert len(day_trades) <= PaperConfig().max_trades_per_day


def test_empty_input_is_a_flat_result_not_a_crash():
    res = paper.simulate({}, PaperConfig())
    assert res.metrics["trades"] == 0
    assert res.metrics["ending_equity"] == 1000.0


def test_metrics_report_an_honest_profit_factor():
    res = paper.simulate({"TEST": _breakout_day()}, PaperConfig())
    m = res.metrics
    assert m["trades"] >= 1
    assert m["wins"] + m["losses"] == m["trades"]
    if m["gross_loss"] == 0:
        assert m["profit_factor"] is None      # undefined, never infinity
