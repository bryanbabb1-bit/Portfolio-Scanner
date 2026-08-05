"""The thesis book runs unattended, so its rules have to be right.

Everything here guards a way an autonomous book could quietly do the wrong
thing: fill twice, trade on fake prices, loosen a stop, or spend money it does
not have.
"""
from __future__ import annotations

import pytest

from app.services import thesis


@pytest.fixture
def book():
    return {"cash": 1000.0, "positions": [], "log": [], "pending": [],
            "started": "2026-08-04"}


def test_staged_orders_fill_at_the_open(book):
    thesis.queue(book, "SMR", 300, "core", "why")
    filled = thesis.execute_pending(book, {"SMR": 10.0})

    assert filled == ["SMR @ 10.00"]
    p = book["positions"][0]
    assert p["entry"] == 10.0
    assert p["shares"] == pytest.approx(30.0)
    assert p["stop"] == pytest.approx(8.0)          # -20% from the fill
    assert book["cash"] == pytest.approx(700.0)


def test_executing_twice_cannot_double_a_position(book):
    thesis.queue(book, "SMR", 300, "core", "why")
    thesis.execute_pending(book, {"SMR": 10.0})
    again = thesis.execute_pending(book, {"SMR": 10.0})

    assert again == []
    assert len(book["positions"]) == 1
    assert book["pending"] == []


def test_an_order_with_no_price_stays_queued(book):
    # Never fill at a guess. It waits.
    thesis.queue(book, "SMR", 300, "core", "why")
    assert thesis.execute_pending(book, {}) == []
    assert len(book["pending"]) == 1


def test_the_book_never_spends_money_it_does_not_have(book):
    thesis.buy(book, "AAA", 900, 10.0, "core", "why")
    thesis.buy(book, "BBB", 500, 10.0, "core", "why")   # only $100 left
    assert book["cash"] >= -1e-9
    assert sum(p["shares"] * p["entry"] for p in book["positions"]) <= 1000 + 1e-6


def test_a_loser_is_cut_at_the_hard_stop(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})        # stop at 80

    acted = thesis.check_stops(book, {"AAA": {"price": 79.0}})
    assert any("STOPPED OUT" in a for a in acted)
    assert book["positions"][0]["closed"]
    assert book["positions"][0]["realized"] < 0


def test_a_position_above_its_stop_is_left_alone(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})
    assert thesis.check_stops(book, {"AAA": {"price": 95.0}}) == []
    assert not book["positions"][0].get("closed")


def test_a_winner_arms_a_trailing_stop_at_plus_fifty(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})

    acted = thesis.check_stops(book, {"AAA": {"price": 160.0}})
    p = book["positions"][0]
    assert p["trimmed"] is True
    assert any("trailing stop armed" in a for a in acted)
    assert p["stop"] == pytest.approx(160.0 * 0.75)     # 25% off the high


def test_the_trailing_stop_ratchets_up_and_never_down(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})
    thesis.check_stops(book, {"AAA": {"price": 200.0}})
    high_stop = book["positions"][0]["stop"]

    # Price pulls back but stays above the stop: the stop must NOT loosen.
    thesis.check_stops(book, {"AAA": {"price": 170.0}})
    assert book["positions"][0]["stop"] == pytest.approx(high_stop)

    # New high ratchets it up.
    thesis.check_stops(book, {"AAA": {"price": 300.0}})
    assert book["positions"][0]["stop"] > high_stop


def test_a_winner_that_reverses_is_stopped_at_the_trail(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})
    thesis.check_stops(book, {"AAA": {"price": 200.0}})   # trail at 150
    acted = thesis.check_stops(book, {"AAA": {"price": 149.0}})

    assert any("STOPPED OUT" in a for a in acted)
    # It still banks a large gain rather than round-tripping to breakeven.
    assert book["positions"][0]["realized"] > 0


def test_mark_reports_progress_against_the_goal(book):
    thesis.queue(book, "AAA", 500, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})
    s = thesis.mark(book, {"AAA": {"price": 120.0}})

    assert s["equity"] == pytest.approx(1100.0)
    assert s["return_pct"] == pytest.approx(10.0)
    assert s["goal"] == thesis.GOAL
    assert s["multiple_needed"] == pytest.approx(round(thesis.GOAL / 1100.0, 1))


def test_mock_prices_are_never_traded_on(monkeypatch):
    # A book that fills against generated data is worse than no book.
    class _MD:
        source = "mock"
        history = None

    from app.services import market_data
    monkeypatch.setattr(market_data, "get_price_data", lambda s: _MD())
    last, opens = thesis._live_quotes(["AAA"])
    assert last == {} and opens == {}


def test_maybe_run_does_nothing_at_the_weekend(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo

    # 2026-08-08 is a Saturday.
    monkeypatch.setattr(thesis, "_et_now",
                        lambda: dt.datetime(2026, 8, 8, 11, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    assert thesis.maybe_run() is None


def test_maybe_run_waits_for_the_open_to_print(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(thesis, "_et_now",
                        lambda: dt.datetime(2026, 8, 4, 9, 31,
                                            tzinfo=ZoneInfo("America/New_York")))
    assert thesis.maybe_run() is None
