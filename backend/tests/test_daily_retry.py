"""Scheduled briefs must not lose the day to a transient advisor failure.

On 2026-07-29 the 16:00 close recap drew a fallback ("Advisor unavailable —
here is the raw setup"), the day was stamped on it, and the window closed with
no real recap and a push whose whole body was "Today's close recap". The very
same build succeeded moments later, so the failure was a CLI hiccup, not an
outage.
"""
from __future__ import annotations

import pytest

from app.services import summary


@pytest.fixture
def at_close(monkeypatch):
    """Freeze the clock inside the close-recap window on a weekday."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # 2026-07-29 is a Wednesday; 16:05 ET is inside the 16:00-17:30 window.
    frozen = datetime(2026, 7, 29, 16, 5, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(summary, "_et_now", lambda: frozen)
    return frozen.strftime("%Y-%m-%d")


def _stub_build(monkeypatch, engine_sequence):
    """Make build() return the given engines in order, recording each call."""
    calls: list[str] = []
    seq = list(engine_sequence)

    def fake_build(kind: str) -> dict:
        calls.append(kind)
        engine = seq.pop(0) if seq else "claude"
        return {"type": kind, "engine": engine, "headline": f"{engine} headline",
                "summary": "s", "watch": [], "recap": [],
                "date": "2026-07-29", "generated_at": "2026-07-29 16:05:00"}

    monkeypatch.setattr(summary, "build", fake_build)
    return calls


def _emitted(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(summary, "_emit", lambda b: sent.append(b))
    return sent


def test_transient_failure_does_not_stamp_the_day(at_close, monkeypatch):
    _stub_build(monkeypatch, ["fallback"])
    sent = _emitted(monkeypatch)

    assert summary.maybe_send_daily() is None
    # Nothing pushed, and the slot stays open for the next heartbeat.
    assert sent == []
    state = summary._load(summary._STATE_FILE, {})
    assert state.get("eod") != at_close
    assert state.get("eod_tries") == f"{at_close}:1"


def test_next_heartbeat_retries_and_delivers(at_close, monkeypatch):
    calls = _stub_build(monkeypatch, ["fallback", "claude"])
    sent = _emitted(monkeypatch)

    assert summary.maybe_send_daily() is None      # hiccup
    brief = summary.maybe_send_daily()             # next heartbeat
    assert brief is not None
    assert brief["engine"] == "claude"
    assert calls == ["eod", "eod"]
    assert len(sent) == 1
    state = summary._load(summary._STATE_FILE, {})
    assert state.get("eod") == at_close
    # The attempt counter is cleared once the day is delivered.
    assert "eod_tries" not in state


def test_a_real_outage_still_delivers_something(at_close, monkeypatch):
    _stub_build(monkeypatch, ["fallback"] * summary.MAX_ADVISOR_ATTEMPTS)
    sent = _emitted(monkeypatch)

    results = [summary.maybe_send_daily() for _ in range(summary.MAX_ADVISOR_ATTEMPTS)]

    # Silence is not an option — the last attempt commits the fallback.
    assert results[:-1] == [None] * (summary.MAX_ADVISOR_ATTEMPTS - 1)
    assert results[-1] is not None
    assert len(sent) == 1
    assert summary._load(summary._STATE_FILE, {}).get("eod") == at_close


def test_delivered_day_is_not_rerun(at_close, monkeypatch):
    _stub_build(monkeypatch, ["claude"])
    sent = _emitted(monkeypatch)
    summary.maybe_send_daily()
    assert len(sent) == 1

    calls = _stub_build(monkeypatch, ["claude"])
    assert summary.maybe_send_daily() is None
    assert calls == []          # build isn't even attempted a second time


def test_stale_attempt_count_does_not_suppress_a_new_day(at_close, monkeypatch):
    # A crash mid-window could leave a counter behind. Yesterday's count must not
    # push today straight to its final attempt.
    summary._save(summary._STATE_FILE, {"eod_tries": "2026-07-28:3"})
    _stub_build(monkeypatch, ["fallback"])
    sent = _emitted(monkeypatch)

    assert summary.maybe_send_daily() is None
    assert sent == []
    assert summary._load(summary._STATE_FILE, {}).get("eod_tries") == f"{at_close}:1"


def test_fallback_push_says_the_advisor_was_unreachable(monkeypatch):
    # The body is what lands on the phone. A fallback that looks like a normal
    # brief is worse than one that admits what happened.
    bodies: list[str] = []
    # Patch the real function, not sys.modules: `from . import push` resolves via
    # the already-imported package attribute once any other test has touched it,
    # so a sys.modules stub passes alone and silently no-ops in a full run.
    from app.services import push as push_service

    monkeypatch.setattr(push_service, "send",
                        lambda title, body, **kw: bodies.append(body))
    monkeypatch.setattr(summary, "_save", lambda *a, **k: None)

    summary._emit({"type": "eod", "engine": "fallback",
                   "headline": "Today's close recap"})
    assert bodies and "Couldn't reach the advisor" in bodies[0]

    bodies.clear()
    summary._emit({"type": "eod", "engine": "claude",
                   "headline": "Red day, VRT earnings gut the book"})
    assert bodies == ["Red day, VRT earnings gut the book"]
