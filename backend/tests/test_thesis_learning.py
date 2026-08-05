"""The book learns from its own record — within limits that matter.

The limits are the point. An agent that can rewrite anything about itself will
eventually rewrite the thesis to match whatever just happened, which is the
opposite of learning.
"""
from __future__ import annotations

import pytest

from app.services import thesis


def _closed(realized: float, n: int = 1) -> list[dict]:
    return [{"symbol": f"S{i}", "shares": 1.0, "entry": 100.0, "opened": "2026-08-04",
             "conviction": "core", "why": "w", "closed": "2026-08-10",
             "exit_price": 100 + realized, "realized": realized}
            for i in range(n)]


def _book(positions: list[dict], **extra) -> dict:
    return {"cash": 0.0, "positions": positions, "log": [], "pending": [],
            "started": "2026-08-04", **extra}


def test_nothing_changes_without_enough_evidence(monkeypatch):
    monkeypatch.setattr(thesis, "load", lambda: _book(_closed(-10, 3)))
    saved = {}
    monkeypatch.setattr(thesis, "save", lambda b: saved.update(b))

    out = thesis.learn(force=True)
    assert out["changes"] == []
    assert "not enough" in out["lessons"][0]["note"]


def test_a_stop_that_keeps_getting_hit_is_widened(monkeypatch):
    # Stopped out of nearly everything: the stop is inside the noise of these
    # names, which is a rule problem rather than a selection problem.
    monkeypatch.setattr(thesis, "load", lambda: _book(_closed(-10, 8)))
    saved: dict = {}
    monkeypatch.setattr(thesis, "save", lambda b: saved.update(b))

    out = thesis.learn(force=True)
    change = out["changes"][0]
    assert change["rule"] == "stop_pct"
    assert change["to"] > change["from"]
    assert "stopped out" in change["why"]
    assert saved["stop_pct"] == change["to"]


def test_a_widened_stop_is_capped(monkeypatch):
    # Learning must not run away: a stop cannot widen without bound just
    # because losses keep arriving.
    monkeypatch.setattr(thesis, "load", lambda: _book(_closed(-10, 8), stop_pct=0.35))
    monkeypatch.setattr(thesis, "save", lambda b: None)
    assert thesis.learn(force=True)["changes"] == []


def test_the_thesis_itself_is_never_edited(monkeypatch):
    monkeypatch.setattr(thesis, "load", lambda: _book(_closed(-10, 12)))
    saved: dict = {}
    monkeypatch.setattr(thesis, "save", lambda b: saved.update(b))
    before = dict(thesis.THESIS)

    thesis.learn(force=True)

    assert thesis.THESIS == before
    assert all(c["rule"] != "thesis" for c in saved.get("rule_changes", []))


def test_every_change_carries_the_evidence_that_caused_it(monkeypatch):
    monkeypatch.setattr(thesis, "load", lambda: _book(_closed(-10, 8)))
    saved: dict = {}
    monkeypatch.setattr(thesis, "save", lambda b: saved.update(b))

    thesis.learn(force=True)
    for c in saved["rule_changes"]:
        assert c["why"] and c["from"] != c["to"]


def test_it_notices_when_the_exits_rather_than_the_entries_are_wrong(monkeypatch):
    # Even-sized winners and losers means the asymmetry is broken.
    positions = _closed(-10, 4) + _closed(10, 4)
    monkeypatch.setattr(thesis, "load", lambda: _book(positions))
    monkeypatch.setattr(thesis, "save", lambda b: None)

    lesson = thesis.learn(force=True)["lessons"][0]
    assert lesson["payoff"] == pytest.approx(1.0)
    assert "exits are the problem" in lesson["note"]


def test_it_recognises_a_working_asymmetry(monkeypatch):
    positions = _closed(-10, 4) + _closed(40, 4)
    monkeypatch.setattr(thesis, "load", lambda: _book(positions))
    monkeypatch.setattr(thesis, "save", lambda b: None)

    lesson = thesis.learn(force=True)["lessons"][0]
    assert lesson["payoff"] > 1
    assert "asymmetry is working" in lesson["note"]


def test_reviews_are_rate_limited(monkeypatch):
    today = thesis._et_now().strftime("%Y-%m-%d")
    monkeypatch.setattr(thesis, "load",
                        lambda: _book(_closed(-10, 8), last_review=today))
    monkeypatch.setattr(thesis, "save", lambda b: None)
    # A rule changed off three days of noise is thrashing, not learning.
    assert thesis.learn() is None
    assert thesis.learn(force=True) is not None


def test_review_reports_the_rule_actually_in_force(monkeypatch):
    monkeypatch.setattr(thesis, "load", lambda: _book([], stop_pct=0.30))
    r = thesis.review()
    assert "-30%" in r["rules_now"]["stop_loss"]
    assert "adjusted" in r["rules_now"]["stop_loss"]
    assert "thesis is out of scope" in r["scope"].lower()


def test_new_fills_use_the_learned_stop_width():
    book = _book([], stop_pct=0.30)
    book["cash"] = 1000.0
    thesis.queue(book, "AAA", 100, "core", "why")
    thesis.execute_pending(book, {"AAA": 100.0})
    assert book["positions"][0]["stop"] == pytest.approx(70.0)


def test_an_unfillable_order_does_not_strand_the_ones_behind_it():
    # An empty book with three staged orders: the first cannot fill, and the
    # run must keep going rather than aborting on it.
    book = _book([])
    book["cash"] = 150.0
    for sym in ("AAA", "BBB", "CCC"):
        thesis.queue(book, sym, 100, "core", "why")

    filled = thesis.execute_pending(book, {"AAA": 10.0, "BBB": 10.0, "CCC": 10.0})

    assert len(filled) == 2                  # $150 buys two $100 orders' worth
    assert len(book["pending"]) == 1         # the third stays queued, not lost
    assert book["cash"] >= -1e-9
