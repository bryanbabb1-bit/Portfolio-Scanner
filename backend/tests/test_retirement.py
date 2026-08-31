"""Rule retirement + scorecard grading integrity.

    cd backend && .venv/Scripts/python -m pytest tests/test_retirement.py -q
"""
import json
import os
from types import SimpleNamespace

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import conviction, scorecard  # noqa: E402


def _ind(**kw):
    base = dict(rsi=50, rsi_prev=50, rsi_min_10d=50, ret_5d_pct=0, ret_20d_pct=0,
                macd=0, macd_signal=0, macd_hist=0, sma20=100, sma50=95,
                sma200=100, ema20=100, atr=2, bb_upper=110, bb_lower=90,
                high_52w=120, low_52w=80, pct_from_52w_high=-10,
                avg_volume_20=1e6, volume_ratio=1.0, trend="downtrend")
    base.update(kw)
    return SimpleNamespace(**base)


def _quote(price=100.0, change_pct=0.0):
    return SimpleNamespace(price=price, change_pct=change_pct, source="live", name=None)


# --------------------------------------------------------------- retirement
def test_retired_rules_do_not_fire_live():
    """A trend-break setup: below the 200-day, death cross, down hard."""
    ind = _ind(sma50=90, sma200=110, trend="downtrend")
    sigs = conviction._detect("TEST", ind, _quote(80, -5), True, None, 40)
    assert not any(s["rule"] in conviction.RETIRED_RULES for s in sigs)


def test_retired_rules_still_fire_for_the_backtest():
    """Retiring must not blind the replay, or the evidence needed to
    un-retire the rule can never accumulate."""
    ind = _ind(sma50=90, sma200=110, trend="downtrend")
    sigs = conviction._detect("TEST", ind, _quote(80, -5), True, None, 40,
                              include_retired=True)
    assert any(s["rule"] == "trend-break" for s in sigs)


def test_the_retired_set_is_exactly_what_the_evidence_condemned():
    """Three sell rules retired on the 5-year replay (2026-07-27), and one buy
    rule retired on its LIVE record (2026-08-31): high-conviction-discovery
    graded 22% win / -0.78% average over 23 firings, the worst in the book."""
    assert conviction.RETIRED_RULES == frozenset(
        {"trend-break", "rsi-sell-zone", "sharp-breakdown",
         "high-conviction-discovery"}
    )


def test_the_retired_discovery_rule_is_still_measured():
    """Retirement suppresses firing, never measurement — deleting the logic
    would destroy the only evidence that could un-retire it."""
    ind = _ind(rsi=55, sma50=101, sma200=99, trend="uptrend",
               pct_from_52w_high=-3, volume_ratio=1.0)
    live = conviction._detect("TEST", ind, _quote(100, 1), False, None, 75)
    replay = conviction._detect("TEST", ind, _quote(100, 1), False, None, 75,
                                include_retired=True)
    assert not any(s["rule"] == "high-conviction-discovery" for s in live)
    assert any(s["rule"] == "high-conviction-discovery" for s in replay)


def test_buy_rules_are_untouched_by_retirement():
    """Retirement hit sell rules only — the buy side must still fire."""
    ind = _ind(rsi=28, sma50=98, sma200=100, trend="uptrend", volume_ratio=1.8)
    sigs = conviction._detect("TEST", ind, _quote(100, 3), True, None, 50)
    assert any(s["side"] == "buy" for s in sigs)


def test_sharp_breakdown_is_suppressed_even_on_a_violent_day():
    ind = _ind(volume_ratio=2.0)
    sigs = conviction._detect("TEST", ind, _quote(100, -12), True, None, 40)
    assert not any(s["rule"] == "sharp-breakdown" for s in sigs)
    with_retired = conviction._detect("TEST", ind, _quote(100, -12), True, None, 40,
                                      include_retired=True)
    assert any(s["rule"] == "sharp-breakdown" for s in with_retired)


# ------------------------------------------------- scorecard grading integrity
@pytest.fixture
def ledger(tmp_path, monkeypatch):
    f = tmp_path / "signal_history.json"
    f.write_text(json.dumps([
        {"id": "REAL:r:2026-01-01", "symbol": "REAL", "side": "buy", "rule": "r",
         "price": 100.0, "ts": 1.0, "date": "2026-01-01"},
        {"id": "GHOST:r:2026-01-01", "symbol": "GHOST", "side": "buy", "rule": "r",
         "price": 100.0, "ts": 1.0, "date": "2026-01-01"},
    ]), encoding="utf-8")
    monkeypatch.setattr(scorecard, "_FILE", f)
    return f


def test_untradeable_symbol_is_reported_not_graded(ledger):
    """The APPL bug: a typo'd ticker has no live price, degrades to mock, and
    a real fired signal gets graded against an invented number."""
    sc = scorecard.compute(price_of=lambda s: 110.0 if s == "REAL" else None)
    assert sc["count"] == 1
    assert sc["ungraded"] == ["GHOST"]


def test_fallback_mock_price_is_refused_in_live_mode(monkeypatch):
    """The guard itself: in auto/live mode a mock source means the live fetch
    FAILED, so its price must never grade a signal."""
    from app.services import market_data

    monkeypatch.setattr(settings, "DATA_MODE", "auto")
    monkeypatch.setattr(
        market_data, "get_price_data",
        lambda sym: SimpleNamespace(source="mock", history=None),
    )
    # price_of=None takes the real code path we are testing.
    assert scorecard.compute()["count"] == 0


def test_configured_mock_mode_still_grades(monkeypatch, ledger):
    """When DATA_MODE really is 'mock' (tests, demos) mock is the expected
    source, not a failure — grading must still work."""
    from app.services import market_data
    import pandas as pd

    monkeypatch.setattr(settings, "DATA_MODE", "mock")
    monkeypatch.setattr(
        market_data, "get_price_data",
        lambda sym: SimpleNamespace(
            source="mock", history=pd.DataFrame({"Close": [111.0]})),
    )
    assert scorecard.compute()["count"] == 2


def test_purge_removes_only_the_named_symbol(ledger):
    assert scorecard.purge("GHOST") == 1
    assert scorecard.purge("GHOST") == 0
    rows = json.loads(ledger.read_text(encoding="utf-8"))
    assert [r["symbol"] for r in rows] == ["REAL"]
