"""The trader writes prose onto a ticket that is already sized and stopped.

The whole risk of a second voice is that it starts moving numbers, so these
tests pin the boundary: a note can change words, never levels, and its
failure modes all end with the ticket exactly as the screen issued it.
"""
from __future__ import annotations

import pytest

from app.services import sleeve, trader


@pytest.fixture(autouse=True)
def _no_push(monkeypatch):
    monkeypatch.setattr(sleeve, "_notify", lambda *a, **k: None)
    monkeypatch.setattr(sleeve, "_core_book_value", lambda: 10_000.0)
    # Another suite disables the advisor process-wide at import time, which
    # silently turned these into "returns None" tests. State it here.
    from app.config import settings
    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)


@pytest.fixture
def ticket():
    book = sleeve._empty()
    t = sleeve.issue("CAPR", "ignition", 7.22, 6.15, book=book, eq=1500,
                     why=["Up 12% today on 4x average volume"], push_it=False)
    sleeve.save(book)
    return t


def _claude(payload: str):
    return lambda prompt, **kw: (payload, "claude")


def test_a_note_changes_words_and_never_levels(monkeypatch, ticket):
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    monkeypatch.setattr(
        "app.services.advisor._run_claude",
        _claude('{"headline": "Volume break on thin float", '
                '"note": "It is running on real participation and sits near the high. '
                'A close back under the trigger says the buyers were one order deep.", '
                '"risk": "2M share float - the spread is the real cost", '
                '"entry": 99.0, "stop": 1.0, "shares": 9999}'))

    before = {k: ticket[k] for k in ("entry", "stop", "target", "shares", "notional", "risk_usd")}
    out = trader.enrich(ticket["id"])
    assert out and out["engine"] == "claude"

    stored = sleeve.get(ticket["id"])
    assert stored["note"].startswith("It is running")
    assert stored["headline"] == "Volume break on thin float"
    assert "float" in stored["note_risk"]
    # The three numbers the model tried to send are on the floor.
    for k, v in before.items():
        assert stored[k] == v


def test_the_advisor_being_off_leaves_the_ticket_alone(monkeypatch, ticket):
    from app.config import settings
    monkeypatch.setattr(settings, "ADVISOR_ENABLED", False)
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    assert trader.enrich(ticket["id"]) is None
    assert sleeve.get(ticket["id"])["note"] == ""


def test_no_budget_means_no_call_and_no_note(monkeypatch, ticket):
    calls: list[str] = []
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: False)
    monkeypatch.setattr("app.services.advisor._run_claude",
                        lambda *a, **k: calls.append("ran") or ("{}", "claude"))
    assert trader.enrich(ticket["id"]) is None
    assert calls == []
    assert sleeve.get(ticket["id"])["note"] == ""


def test_unparseable_output_leaves_the_ticket_as_issued(monkeypatch, ticket):
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    monkeypatch.setattr("app.services.advisor._run_claude",
                        _claude("I think this looks like a decent setup, maybe."))
    assert trader.enrich(ticket["id"]) is None
    stored = sleeve.get(ticket["id"])
    assert stored["note"] == "" and stored["why"]


def test_an_empty_note_is_not_written(monkeypatch, ticket):
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    monkeypatch.setattr("app.services.advisor._run_claude",
                        _claude('{"headline": "Something", "note": "", "risk": ""}'))
    assert trader.enrich(ticket["id"]) is None
    assert sleeve.get(ticket["id"])["headline"] != "Something"


def test_a_ticket_is_never_enriched_twice(monkeypatch, ticket):
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    monkeypatch.setattr("app.services.advisor._run_claude",
                        _claude('{"headline": "First", "note": "One. Two.", "risk": "r"}'))
    assert trader.enrich(ticket["id"])
    monkeypatch.setattr("app.services.advisor._run_claude",
                        _claude('{"headline": "Second", "note": "Three. Four.", "risk": "r"}'))
    assert trader.enrich(ticket["id"]) is None
    assert sleeve.get(ticket["id"])["headline"] == "First"


def test_a_filled_ticket_is_not_re_narrated(monkeypatch, ticket):
    """Once it is a position the note is history; rewriting it would let a
    later call describe a trade the client is already in."""
    monkeypatch.setattr("app.services.budget.take", lambda *a, **k: True)
    monkeypatch.setattr("app.services.advisor._run_claude",
                        _claude('{"headline": "Late", "note": "One. Two.", "risk": "r"}'))
    sleeve.confirm_fill(ticket["id"], 7.30)
    assert trader.enrich(ticket["id"]) is None


def test_the_persona_forbids_the_hedging_words_that_broke_the_runner_alerts():
    """Not a style preference: 27 of 33 runner alerts came back as warnings
    because the growth persona hedged them. The trader is told not to."""
    p = trader.PERSONA.lower()
    assert "consider" in p and "not instructions" in p
    assert "never argue for widening a stop" in p
    assert "you are not" in p                      # explicitly not the advisor


def test_the_overnight_desk_argues_open_tickets_before_holdings(monkeypatch):
    from app.services import nightly
    book = sleeve._empty()
    t = sleeve.issue("CAPR", "ignition", 7.22, 6.15, book=book, eq=1500, push_it=False)
    t["status"] = "live"
    sleeve.save(book)
    monkeypatch.setattr("app.services.debate.get_cached", lambda *a, **k: None)

    ranked = nightly._sleeve_first([{"symbol": "NVDA", "score": 40.0, "why": ["live signal"]}])
    assert [c["symbol"] for c in ranked] == ["CAPR", "NVDA"]
    assert ranked[0]["why"] == ["open sleeve ticket"]


def test_a_name_that_is_both_a_holding_and_a_ticket_is_queued_once(monkeypatch):
    from app.services import nightly
    book = sleeve._empty()
    t = sleeve.issue("NVDA", "pullback", 200.0, 180.0, book=book, eq=1500, push_it=False)
    t["status"] = "live"
    sleeve.save(book)
    monkeypatch.setattr("app.services.debate.get_cached", lambda *a, **k: None)

    ranked = nightly._sleeve_first([{"symbol": "NVDA", "score": 40.0, "why": ["live signal"]}])
    assert [c["symbol"] for c in ranked] == ["NVDA"]
