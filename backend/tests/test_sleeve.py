"""The sleeve issues real money instructions unattended, so every rule that
could quietly do the wrong thing is pinned here: over-sizing, ticketing a
name that already ran, managing on fake prices, loosening a stop, signalling
the same exit twice, or grading a trade against the wrong fill.
"""
from __future__ import annotations

import time

import pytest

from app.services import sleeve


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(sleeve, "_notify",
                        lambda title, body, sound, data: sent.append(
                            {"title": title, "body": body, "sound": sound, "data": data}))
    monkeypatch.setattr(sleeve, "_core_book_value", lambda: 10_000.0)
    sleeve._LAST_SCAN["ts"] = 0.0
    yield sent


@pytest.fixture
def book():
    return sleeve._empty()


CFG = dict(sleeve.DEFAULTS)


# ------------------------------------------------------------------ sizing
def test_risk_based_size_shrinks_with_a_wider_stop():
    tight = sleeve.size(100, 88, 1500, "pullback", CFG)
    wide = sleeve.size(100, 80, 1500, "pullback", CFG)
    assert tight["risk_usd"] == pytest.approx(75, abs=0.5)      # 5% of 1500, cap not binding
    assert wide["shares"] < tight["shares"]
    assert wide["risk_usd"] <= 75 + 0.01


def test_position_is_capped_by_slots_and_runner_cap():
    # 5% risk on a 2% stop wants a $3,750 position — the slot cap says $750.
    s = sleeve.size(100, 98, 1500, "pullback", CFG)
    assert s["notional"] == pytest.approx(750, abs=0.01)
    # A runner is additionally capped at 25% of the sleeve.
    r = sleeve.size(10, 8.2, 1500, "ignition", CFG)
    assert r["notional"] <= 375 + 0.01


def test_bad_levels_size_to_zero():
    assert sleeve.size(10, 12, 1500, "manual", CFG)["shares"] == 0
    assert sleeve.size(10, 8, 0, "manual", CFG)["shares"] == 0


def test_capital_percent_of_core_or_explicit_dollars():
    assert sleeve.capital({"capital_pct": 15.0, "capital_usd": None}) == pytest.approx(1500)
    assert sleeve.capital({"capital_pct": 15.0, "capital_usd": 2000}) == 2000


# ----------------------------------------------------------------- issuing
def test_issue_creates_an_armed_ticket_and_pushes_the_verb_first(book, _quiet):
    t = sleeve.issue("CAPR", "ignition", 7.22, 6.15, book=book, eq=1500)
    assert t and t["status"] == "armed"
    assert t["target"] == pytest.approx(7.22 + 3 * (7.22 - 6.15), abs=0.001)
    assert t["shares"] > 0 and t["notional"] <= 375.01
    assert _quiet and _quiet[0]["title"].startswith("BUY CAPR")
    assert _quiet[0]["sound"] == "runner.wav"
    assert _quiet[0]["data"]["type"] == "ticket"


def test_no_duplicate_open_ticket_for_a_symbol(book):
    assert sleeve.issue("CAPR", "ignition", 7.22, 6.15, book=book, eq=1500)
    assert sleeve.issue("CAPR", "ignition", 7.30, 6.20, book=book, eq=1500) is None


def test_daily_cap_holds_but_manual_tickets_bypass_it(book):
    for i, sym in enumerate(("AAA", "BBB", "CCC")):
        assert sleeve.issue(sym, "ignition", 10, 8.2, book=book, eq=1500)
    assert sleeve.issue("DDD", "ignition", 10, 8.2, book=book, eq=1500) is None
    assert sleeve.issue("EEE", "manual", 10, 8.2, book=book, eq=1500)


def test_disabled_sleeve_issues_nothing(book):
    book["config"] = {"enabled": False}
    assert sleeve.issue("CAPR", "ignition", 7.22, 6.15, book=book, eq=1500) is None


def test_ignition_never_tickets_an_extended_name(book):
    movers = [
        {"symbol": "RUN", "stage": "igniting", "price": 5.0, "change_pct": 12,
         "rvol": 4.0, "market_cap": 3e8, "name": "Runner Inc"},
        {"symbol": "TOP", "stage": "extended", "price": 9.0, "change_pct": 61,
         "rvol": 12.0, "market_cap": 3e8, "name": "Already Ran"},
    ]
    issued = sleeve.from_ignition(movers, book=book, eq=1500, push_it=False)
    assert [t["symbol"] for t in issued] == ["RUN"]
    t = issued[0]
    assert t["stop"] == pytest.approx(5.0 * (1 - CFG["ignition_stop_pct"]), abs=0.001)


# ---------------------------------------------------------------- lifecycle
def _armed(book, sym="CAPR", entry=10.0, stop=8.2):
    return sleeve.issue(sym, "ignition", entry, stop, book=book, eq=1500, push_it=False)


def test_armed_ticket_expires_at_the_close_silently(book, _quiet):
    t = _armed(book)
    t["expires"] = time.time() - 1
    gone = sleeve.expire(book)
    assert gone == ["CAPR"] and t["status"] == "expired"
    assert _quiet == []


def test_fill_keeps_the_planned_stop_distance_from_the_real_fill(book, monkeypatch):
    t = _armed(book, entry=10.0, stop=8.2)
    sleeve.save(book)
    live = sleeve.confirm_fill(t["id"], 10.3)
    assert live["status"] == "live"
    assert live["fill_price"] == 10.3
    assert live["stop"] == pytest.approx(10.3 - 1.8, abs=0.001)
    assert live["current_stop"] == live["stop"]
    assert live["r_unit"] == pytest.approx(1.8, abs=0.001)
    assert live["target"] == pytest.approx(10.3 + 3 * 1.8, abs=0.001)


def test_fill_and_pass_only_apply_to_armed_tickets(book):
    t = _armed(book)
    sleeve.save(book)
    sleeve.pass_ticket(t["id"])
    with pytest.raises(ValueError):
        sleeve.confirm_fill(t["id"], 10.0)
    with pytest.raises(KeyError):
        sleeve.pass_ticket("tk_nope")


def _live(book, sym="CAPR", fill=10.0, stop=8.2):
    t = _armed(book, sym=sym, entry=fill, stop=stop)
    t["status"] = "live"
    t["fill_price"] = fill
    t["fill_day"] = "2026-08-28"
    t["current_stop"] = stop
    t["high_water"] = fill
    t["r_unit"] = fill - stop
    return t


def test_plus_one_r_moves_stop_to_breakeven_and_arms_the_trail(book):
    t = _live(book)                                   # R = 1.8
    ev = sleeve.manage(book, {"CAPR": {"price": 11.9, "source": "live"}}, CFG, today="2026-08-29")
    assert [e["kind"] for e in ev] == ["trail_armed"]
    assert t["trail_armed"] is True
    assert t["current_stop"] >= 10.0                  # never below the fill


def test_trail_ratchets_up_only(book):
    t = _live(book)
    sleeve.manage(book, {"CAPR": {"price": 14.0, "source": "live"}}, CFG, today="2026-08-29")
    stop_at_14 = t["current_stop"]
    assert stop_at_14 == pytest.approx(14.0 * 0.75, abs=0.001)
    sleeve.manage(book, {"CAPR": {"price": 12.0, "source": "live"}}, CFG, today="2026-08-29")
    assert t["current_stop"] == stop_at_14              # a pullback does not lower it
    assert t["status"] == "live"                        # 12.0 > 10.5, still in


def test_stop_hit_signals_exit_exactly_once(book, _quiet):
    t = _live(book)
    ev1 = sleeve.manage(book, {"CAPR": {"price": 8.1, "source": "live"}}, CFG, today="2026-08-29")
    sleeve._push_events(ev1)
    ev2 = sleeve.manage(book, {"CAPR": {"price": 7.9, "source": "live"}}, CFG, today="2026-08-29")
    assert [e["reason"] for e in ev1] == ["stop"]
    assert ev2 == []                                    # status is 'exit', not re-signalled
    assert t["status"] == "exit"
    assert len(_quiet) == 1 and _quiet[0]["title"].startswith("SELL CAPR now")
    assert _quiet[0]["sound"] == "sell.wav"


def test_target_hit_signals_exit(book):
    t = _live(book)                                    # target = 10 + 3*1.8 = 15.4
    ev = sleeve.manage(book, {"CAPR": {"price": 15.5, "source": "live"}}, CFG, today="2026-08-29")
    assert any(e.get("reason") == "target" for e in ev)
    assert t["status"] == "exit"


def test_time_stop_flattens_a_runner_that_has_not_paid(book):
    t = _live(book)
    for day in ("2026-08-29", "2026-09-01", "2026-09-02"):
        ev = sleeve.manage(book, {"CAPR": {"price": 10.2, "source": "live"}}, CFG, today=day)
    assert t["sessions_held"] == 3
    assert [e["reason"] for e in ev] == ["time"]


def test_mock_prices_never_manage_a_live_ticket(book):
    t = _live(book)
    ev = sleeve.manage(book, {"CAPR": {"price": 1.0, "source": "mock"}}, CFG, today="2026-08-29")
    assert ev == [] and t["status"] == "live" and t["current_stop"] == 8.2


def test_close_grades_in_r_off_the_actual_fill(book):
    t = _live(book, fill=10.0, stop=8.2)
    sleeve.save(book)
    done = sleeve.close(t["id"], 13.6, "manual")
    assert done["status"] == "closed"
    assert done["r_multiple"] == pytest.approx(2.0, abs=0.01)
    assert done["pnl_usd"] == pytest.approx(3.6 * t["shares"], abs=0.01)


def test_scorecard_reports_n_beside_expectancy(book):
    for sym, r in (("A", 2.0), ("B", -1.0), ("C", 0.5)):
        t = _live(book, sym=sym)
        sleeve._grade(t, t["fill_price"] + r * t["r_unit"], "manual")
    sc = sleeve.scorecard(book)["ignition"]
    assert sc["n"] == 3 and sc["wins"] == 2
    assert sc["expectancy_r"] == pytest.approx(0.5, abs=0.001)
    assert sc["t_stat"] is not None


def test_equity_counts_realized_and_open_pnl(book):
    t = _live(book, fill=10.0, stop=8.2)
    won = _live(book, sym="WIN", fill=20.0, stop=17.0)
    sleeve._grade(won, 26.0, "target")
    eq = sleeve.equity(book, {"CAPR": {"price": 11.0}}, cap=1500)
    assert eq == pytest.approx(1500 + won["pnl_usd"] + 1.0 * t["shares"], abs=0.01)


def test_config_clamps_and_ignores_unknown_keys():
    cfg = sleeve.set_config({"risk_pct": 99, "max_slots": 0, "bogus": 1, "capital_usd": 0})
    assert cfg["risk_pct"] == 25.0
    assert cfg["max_slots"] == 1
    assert cfg["capital_usd"] is None
    assert "bogus" not in cfg


def test_after_hours_ticket_expires_at_the_next_sessions_close():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    fri_evening = datetime(2026, 8, 28, 18, 30, tzinfo=et)     # Friday after the close
    ts = sleeve._session_close_ts(fri_evening)
    when = datetime.fromtimestamp(ts, et)
    assert when.weekday() == 0 and when.hour == 16              # Monday 16:00


def test_tickets_issue_pre_market_through_the_close_only():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    assert sleeve.issue_window(datetime(2026, 8, 31, 7, 5, tzinfo=et))       # pre-market gapper
    assert sleeve.issue_window(datetime(2026, 8, 31, 15, 59, tzinfo=et))
    assert not sleeve.issue_window(datetime(2026, 8, 31, 17, 30, tzinfo=et))  # after hours
    assert not sleeve.issue_window(datetime(2026, 8, 29, 10, 0, tzinfo=et))   # Saturday


# ------------------------------------------------------- conditional watches
def _accum_row(sym="SY", price=2.90, trigger=3.10, ratio=37.0, beaten=True):
    return {"symbol": sym, "price": price, "trigger_above": trigger,
            "vol_ratio": ratio, "beaten_down": beaten, "drift_20d": -16.0,
            "avg_dollar_vol": 1_100_000, "loud": True}


def test_a_footprint_name_is_a_watch_not_an_order(book, _quiet):
    issued = sleeve.from_footprint([_accum_row()], book=book, eq=1500)
    assert len(issued) == 1
    t = issued[0]
    assert t["status"] == "watching"
    assert t["trigger_above"] == 3.10
    assert t["engine"] == "footprint"
    assert _quiet == []                    # a watch is not news
    assert any("No break, no trade" in w for w in t["why"])


def test_a_trigger_already_behind_us_is_not_a_trigger(book):
    # Price has already run through yesterday's high — the level says nothing.
    assert sleeve.from_footprint([_accum_row(price=3.50, trigger=3.10)],
                                 book=book, eq=1500) == []


def test_a_watch_arms_and_pushes_only_when_the_level_trades(book, _quiet):
    t = sleeve.from_footprint([_accum_row()], book=book, eq=1500)[0]
    planned = t["entry"] - t["stop"]

    quiet_day = sleeve.check_triggers(book, {"SY": {"price": 3.00, "source": "live"}}, CFG, eq=1500)
    assert quiet_day == [] and t["status"] == "watching" and _quiet == []

    fired = sleeve.check_triggers(book, {"SY": {"price": 3.24, "source": "live"}}, CFG, eq=1500)
    sleeve._push_events(fired)
    assert [e["kind"] for e in fired] == ["triggered"]
    assert t["status"] == "armed"
    assert t["entry"] == 3.24                       # a gap through is not a fill at the level
    assert t["stop"] == pytest.approx(3.24 - planned, abs=0.001)
    assert t["shares"] > 0 and t["risk_usd"] <= 75.01
    assert len(_quiet) == 1 and _quiet[0]["title"].startswith("BUY SY")


def test_a_watch_that_never_breaks_expires_quietly(book, _quiet):
    t = sleeve.from_footprint([_accum_row()], book=book, eq=1500)[0]
    t["expires"] = time.time() - 1
    assert sleeve.expire(book) == ["SY"]
    assert t["status"] == "expired" and _quiet == []


def test_a_watch_blocks_a_second_ticket_on_the_same_name(book):
    sleeve.from_footprint([_accum_row()], book=book, eq=1500)
    assert sleeve.issue("SY", "ignition", 3.0, 2.5, book=book, eq=1500) is None


def test_mock_quotes_never_trigger_a_watch(book):
    t = sleeve.from_footprint([_accum_row()], book=book, eq=1500)[0]
    assert sleeve.check_triggers(book, {"SY": {"price": 9.9, "source": "mock"}}, CFG, eq=1500) == []
    assert t["status"] == "watching"


def test_a_swing_that_stalls_for_twenty_sessions_is_recycled(book):
    t = _live(book, sym="SWG", fill=100.0, stop=90.0)
    t["engine"] = "pullback"
    seen: list[dict] = []
    for i in range(22):
        day = f"2026-09-{i + 1:02d}"
        seen += sleeve.manage(book, {"SWG": {"price": 101.0, "source": "live"}}, CFG, today=day)
    # Exactly one exit, raised once, at the hold limit — not every pass after it.
    assert [e["reason"] for e in seen] == ["time"]
    assert t["status"] == "exit"
    assert t["sessions_held"] == CFG["pullback_max_hold_sessions"]


# ------------------------------------------------------------- benchmark
def test_the_curve_never_reports_a_return_without_the_index(monkeypatch):
    curve = [{"day": "2026-08-03", "equity": 1000.0}, {"day": "2026-08-04", "equity": 1100.0}]

    class _MD:
        source = "live"
        history = None

    import pandas as pd
    idx = pd.to_datetime(["2026-08-03", "2026-08-04"])
    _MD.history = pd.DataFrame({"Close": [500.0, 505.0]}, index=idx)
    monkeypatch.setattr("app.services.market_data.get_price_data", lambda s: _MD())

    bench, note = sleeve._benchmark(curve, 1000.0)
    assert [b["equity"] for b in bench] == [1000.0, 1010.0]   # rebased to the sleeve
    assert "SPY +1.0%" in note and "ahead of" in note


def test_a_failed_benchmark_fetch_says_so_instead_of_faking_it(monkeypatch):
    def _boom(_):
        raise RuntimeError("no network")
    monkeypatch.setattr("app.services.market_data.get_price_data", _boom)
    bench, note = sleeve._benchmark(
        [{"day": "2026-08-03", "equity": 1000.0}, {"day": "2026-08-04", "equity": 1100.0}], 1000.0)
    assert bench == [] and "not being faked" in note


def test_changing_the_capital_re_sizes_what_is_not_yet_committed(book, monkeypatch):
    """A watch and an unfilled order are instructions, not positions. If the
    sleeve doubles, the blotter must not keep showing the old dollar figure —
    it would disagree with what the engine would actually do at the trigger."""
    monkeypatch.setattr(sleeve, "capital", lambda *a, **k: 2000.0)
    watch = sleeve.from_footprint([_accum_row()], book=book, eq=1000)[0]
    armed = _armed(book, sym="RUN", entry=10.0, stop=8.2)
    live = _live(book, sym="HELD", fill=50.0, stop=45.0)
    before = {"entry": watch["entry"], "stop": watch["stop"]}
    live_size = live["shares"]

    touched = sleeve.resize_open(book)

    assert set(touched) == {"SY", "RUN"}
    # Levels are what the setup said; only the size follows the money.
    assert watch["entry"] == before["entry"] and watch["stop"] == before["stop"]
    assert watch["risk_usd"] == pytest.approx(100, abs=0.5)     # 5% of 2000
    assert armed["sleeve_equity"] == 2000.0
    # A position already opened is NOT re-sized — those shares are real.
    assert live["shares"] == live_size
