"""Overnight desk pre-load: spend calls only where there is something new.

Each test pins a way this could quietly become "debate everything nightly",
which the measured cost (394k tokens a session) makes unaffordable.
"""
from __future__ import annotations

import time
import types

import pytest

from app.services import nightly


def _report(sym, *, shares=1.0, change_pct=0.0, pl_pct=0.0, dte=None, source="live"):
    return types.SimpleNamespace(
        symbol=sym, shares=shares, days_to_earnings=dte,
        unrealized_pl_pct=pl_pct,
        quote=types.SimpleNamespace(change_pct=change_pct, source=source),
    )


@pytest.fixture(autouse=True)
def _no_cache_no_stance(monkeypatch):
    from app.services import debate, stance
    monkeypatch.setattr(debate, "get_cached", lambda s, max_age=0: None)
    monkeypatch.setattr(stance, "get", lambda s: None)


def test_a_recently_debated_name_is_skipped_so_the_book_rotates(monkeypatch):
    from app.services import debate
    fresh = {"ts": time.time() - 86400}          # debated yesterday
    monkeypatch.setattr(debate, "get_cached", lambda s, max_age=0: fresh)
    assert nightly.score_candidates([_report("NVDA", dte=1)]) == []


def test_earnings_this_week_outranks_a_quiet_name():
    ranked = nightly.score_candidates([
        _report("QUIET"),
        _report("SOON", dte=2),
    ])
    assert ranked[0]["symbol"] == "SOON"
    assert any("earnings" in w for w in ranked[0]["why"])


def test_a_live_signal_is_the_strongest_reason():
    ranked = nightly.score_candidates(
        [_report("AAA", dte=10), _report("BBB")],
        signals=[{"symbol": "BBB"}],
    )
    assert ranked[0]["symbol"] == "BBB"
    assert "live signal" in ranked[0]["why"]


def test_a_big_move_earns_a_seat():
    ranked = nightly.score_candidates([_report("AAA"), _report("MOVER", change_pct=-7.5)])
    assert ranked[0]["symbol"] == "MOVER"
    assert any("moved" in w for w in ranked[0]["why"])


def test_a_standing_sell_still_held_is_a_contradiction_worth_settling(monkeypatch):
    from app.services import stance
    monkeypatch.setattr(stance, "get",
                        lambda s: {"action": "SELL"} if s == "STALE" else None)
    ranked = nightly.score_candidates([_report("AAA"), _report("STALE")])
    assert ranked[0]["symbol"] == "STALE"
    assert any("still held" in w for w in ranked[0]["why"])


def test_watchlist_names_are_not_debated():
    # Only positions. Debating something you do not own is the easiest way to
    # spend the whole budget on nothing.
    assert nightly.score_candidates([_report("WATCH", shares=0)]) == []


def test_every_candidate_says_why_it_was_picked():
    ranked = nightly.score_candidates([_report("AAA", dte=3, change_pct=6.0)])
    assert ranked[0]["why"], "a pick with no reason is not inspectable"
    assert ranked[0]["score"] > 0


def test_it_does_nothing_outside_the_overnight_window(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo
    # 11:00 ET on a Wednesday — market hours, must not compete for the CLI.
    monkeypatch.setattr(nightly, "_et_now",
                        lambda: dt.datetime(2026, 8, 12, 11, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    assert nightly.maybe_run() is None


def test_it_does_not_run_twice_in_one_night(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(nightly, "_et_now",
                        lambda: dt.datetime(2026, 8, 12, 19, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    monkeypatch.setattr(nightly, "_load_state", lambda: {"last_run": "2026-08-12"})
    assert nightly.maybe_run() is None


def test_it_stays_quiet_at_the_weekend(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo
    # Saturday evening: nothing has changed since Friday's close.
    monkeypatch.setattr(nightly, "_et_now",
                        lambda: dt.datetime(2026, 8, 15, 19, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    monkeypatch.setattr(nightly, "_load_state", lambda: {})
    assert nightly.maybe_run() is None


def test_the_nightly_budget_is_capped(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo
    from app.services import conviction, debate, portfolio as pf

    many = [_report(f"S{i}", dte=1, change_pct=9.0) for i in range(20)]
    monkeypatch.setattr(nightly, "_et_now",
                        lambda: dt.datetime(2026, 8, 12, 19, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    monkeypatch.setattr(nightly, "_load_state", lambda: {})
    monkeypatch.setattr(nightly, "_save_state", lambda d: None)
    monkeypatch.setattr(pf, "portfolio_summary", lambda: (None, many))
    monkeypatch.setattr(conviction, "scan", lambda: [])

    called: list[str] = []

    def _convene(sym, force=False):
        called.append(sym)
        return {"verdict": {"ruling": "HOLD"}}

    monkeypatch.setattr(debate, "convene", _convene)
    monkeypatch.setattr(nightly, "MAX_PER_NIGHT", 4)

    out = nightly.maybe_run()
    assert len(called) == 4, "twenty eligible names must still cost four sessions"
    assert len(out["ran"]) == 4


def test_mock_priced_names_are_never_debated(monkeypatch):
    import datetime as dt
    from zoneinfo import ZoneInfo
    from app.services import conviction, debate, portfolio as pf

    monkeypatch.setattr(nightly, "_et_now",
                        lambda: dt.datetime(2026, 8, 12, 19, 0,
                                            tzinfo=ZoneInfo("America/New_York")))
    monkeypatch.setattr(nightly, "_load_state", lambda: {})
    monkeypatch.setattr(nightly, "_save_state", lambda d: None)
    monkeypatch.setattr(pf, "portfolio_summary",
                        lambda: (None, [_report("FAKE", dte=1, source="mock")]))
    monkeypatch.setattr(conviction, "scan", lambda: [])
    called: list[str] = []
    monkeypatch.setattr(debate, "convene",
                        lambda s, force=False: called.append(s))

    nightly.maybe_run()
    assert called == [], "a debate off generated prices reasons about nothing"
