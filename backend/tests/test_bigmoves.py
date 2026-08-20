"""Whole-market big-move alerts: rare enough to still be read.

    cd backend && .venv/Scripts/python -m pytest tests/test_bigmoves.py -q
"""
import os
import time

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import bigmoves as bm  # noqa: E402


def _row(sym, chg, price=50.0, avg_vol=10_000_000):
    return {"symbol": sym, "name": sym, "change_pct": chg, "price": price,
            "avg_vol": avg_vol, "market_cap": None, "volume": None}


# ------------------------------------------------------------------ tiering
def test_the_mrna_shape_clears_the_loud_bar():
    # $426M/day traded before it doubled. This is the one to be woken for.
    assert bm.classify(_row("MRNA", 177.0, price=174.0, avg_vol=9_600_000)) == "alert"


def test_a_pumped_shell_never_clears_it():
    """The dollar-volume floor is doing as much work as the move.

    A stock that traded $40k a day and is up 300% is not a company being
    repriced. Judging it on today's volume would let it through, which is why
    the floor uses the AVERAGE volume at the PRE-move price.
    """
    assert bm.classify(_row("SHELL", 300.0, price=1.2, avg_vol=30_000)) is None


def test_a_real_company_moving_hard_is_notable_but_not_a_push():
    # +16% on a liquid name is a real event and a terrible notification: it
    # happened 6.3 times a session in the measured window.
    assert bm.classify(_row("BIGCO", 16.0, price=80.0, avg_vol=5_000_000)) == "big"


def test_a_smaller_name_really_ripping_is_its_own_tier():
    assert bm.classify(_row("SMALLCO", 30.0, price=8.0, avg_vol=400_000)) == "runner"


def test_a_penny_stock_ripping_is_not_a_runner():
    assert bm.classify(_row("PENNY", 40.0, price=1.5, avg_vol=400_000)) is None


def test_prior_dollar_volume_uses_the_price_before_the_move():
    """Today's spike must not qualify the name that caused it."""
    row = _row("X", 100.0, price=20.0, avg_vol=1_000_000)   # doubled from $10
    assert round(bm._prior_dollar_volume(row)) == 10_000_000


# --------------------------------------------------------------------- push
@pytest.fixture
def stub(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "_FILE", tmp_path / "bigmoves.json")
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda title, body, **k: sent.append((title, body)) or {})
    # Before the digest hour, so digest logic never fires in these tests.
    class _ET:
        hour = 11
        def strftime(self, f): return "2026-08-20"
    monkeypatch.setattr(bm, "_et", lambda: _ET())
    return sent


def test_only_the_loud_tier_buzzes(stub, monkeypatch):
    monkeypatch.setattr(bm, "_scan_market", lambda: [
        _row("LOUD", 60.0, price=30.0, avg_vol=5_000_000),
        _row("BIGCO", 16.0, price=80.0, avg_vol=5_000_000),
        _row("SMALLCO", 30.0, price=8.0, avg_vol=400_000),
    ])
    monkeypatch.setattr(bm, "_why", lambda s: "Some headline")
    out = bm.scan(force=True)
    assert len(stub) == 1 and "LOUD" in stub[0][0]
    assert {r["tier"] for r in out["movers"]} == {"alert", "big", "runner"}


def test_the_same_name_does_not_buzz_twice_in_a_session(stub, monkeypatch):
    monkeypatch.setattr(bm, "_scan_market",
                        lambda: [_row("LOUD", 60.0, price=30.0, avg_vol=5_000_000)])
    monkeypatch.setattr(bm, "_why", lambda s: "")
    bm.scan(force=True)
    bm.scan(force=True)          # still running, still up 60%
    assert len(stub) == 1


def test_a_new_session_forgets_yesterdays_pushes(stub, monkeypatch):
    monkeypatch.setattr(bm, "_scan_market",
                        lambda: [_row("LOUD", 60.0, price=30.0, avg_vol=5_000_000)])
    monkeypatch.setattr(bm, "_why", lambda s: "")
    bm.scan(force=True)
    assert len(stub) == 1

    class _Tomorrow:
        hour = 11
        def strftime(self, f): return "2026-08-21"
    monkeypatch.setattr(bm, "_et", lambda: _Tomorrow())
    bm.scan(force=True)
    assert len(stub) == 2        # a fresh +60% day is a fresh event


def test_the_headline_rides_along_because_why_is_the_whole_question(stub, monkeypatch):
    """A Phase 3 readout and a promotional press release both print +60%.

    The headline is what lets Bryan tell a durable story from a pump, which is
    the entire difference between a rally worth joining and a bag.
    """
    monkeypatch.setattr(bm, "_scan_market",
                        lambda: [_row("LOUD", 60.0, price=30.0, avg_vol=5_000_000)])
    monkeypatch.setattr(bm, "_why", lambda s: "Phase 3 trial met primary endpoint")
    bm.scan(force=True)
    assert "Phase 3" in stub[0][1]


def test_a_broad_tape_sends_one_digest_not_sixty_pushes(monkeypatch, tmp_path):
    """2026-07-30: sixty names moved 15%+ on a sector melt-up. Sixty pushes is
    how a notification channel gets muted, and a muted channel cannot deliver
    the one that counts."""
    monkeypatch.setattr(bm, "_FILE", tmp_path / "b.json")
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda title, body, **k: sent.append((title, body)) or {})

    class _Close:
        hour = 16
        def strftime(self, f): return "2026-07-30"
    monkeypatch.setattr(bm, "_et", lambda: _Close())
    monkeypatch.setattr(bm, "_scan_market", lambda: [
        _row(f"S{i}", 16.0 + i * 0.1, price=80.0, avg_vol=5_000_000)
        for i in range(60)
    ])
    out = bm.scan(force=True)
    assert out["cluster"] is True
    assert len(sent) == 1
    assert "Broad move" in sent[0][1]
    assert "60 names" in sent[0][1]
    # Never a bare count: the digest names the biggest ones.
    assert "S59" in sent[0][1]


def test_the_digest_goes_out_once(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "_FILE", tmp_path / "b.json")
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda title, body, **k: sent.append(title) or {})

    class _Close:
        hour = 16
        def strftime(self, f): return "2026-08-20"
    monkeypatch.setattr(bm, "_et", lambda: _Close())
    monkeypatch.setattr(bm, "_scan_market",
                        lambda: [_row("BIGCO", 16.0, price=80.0, avg_vol=5_000_000)])
    bm.scan(force=True)
    bm.scan(force=True)
    assert sent.count("MOVERS TODAY") == 1


def test_nothing_moving_means_nothing_sent(stub, monkeypatch):
    monkeypatch.setattr(bm, "_scan_market", lambda: [_row("FLAT", 2.0)])
    out = bm.scan(force=True)
    assert out["movers"] == []
    assert stub == []
