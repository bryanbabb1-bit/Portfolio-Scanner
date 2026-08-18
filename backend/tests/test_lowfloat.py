"""The five-filter low-float screen.

The thresholds are the product here, so each one gets a test that fails if it
silently loosens.
"""
from __future__ import annotations

import pytest

from app.services import lowfloat as lf


def test_the_originally_stated_screen_is_preserved_verbatim():
    # Kept as a baseline so any loosening reads as a deviation rather than
    # quietly becoming the new normal.
    assert lf.STATED == {"max_price": 20.0, "min_rvol": 2.0,
                         "min_volume": 4_000_000, "max_float": 20_000_000,
                         "max_cap": 2_000_000_000}


def test_float_stays_at_the_stated_threshold():
    # An earlier calibration loosened this to 150M off a 90-name sample. At full
    # coverage the stated screen fires ~24 times a day, so the loosening was
    # solving a problem that only existed because the universe was too small.
    assert lf.MAX_FLOAT == lf.STATED["max_float"] == 20_000_000
    assert lf.describe()["loosened_from_stated"] is False


def test_the_narrowing_lever_is_the_price_floor():
    assert lf.MIN_PRICE == 3.00
    assert "price floor" in lf.describe()["narrowing"]


def test_a_sub_dollar_churner_is_excluded(monkeypatch):
    # 400x rvol on a $0.15 stock is dilution churn, not a squeeze.
    out = _run(monkeypatch, [_quote(regularMarketPrice=0.15,
                                    averageDailyVolume3Month=20_000)],
               {"AAA": {"float_shares": 5_000_000}})
    assert out["results"] == []


def test_every_threshold_is_overridable(monkeypatch):
    # Loosening back is a query parameter, never an edit.
    out = _run(monkeypatch, [_quote()], {"AAA": {"float_shares": 45_000_000}},
               max_float=50_000_000)
    assert [r["symbol"] for r in out["results"]] == ["AAA"]


def test_relative_volume_is_against_the_name_s_own_average():
    # 2x of ITS OWN normal, not a big absolute number — that is the whole point
    # of rvol over a raw volume filter.
    assert lf._rvol({"regularMarketVolume": 8_000_000,
                     "averageDailyVolume3Month": 4_000_000}) == pytest.approx(2.0)
    assert lf._rvol({"regularMarketVolume": 8_000_000}) is None
    assert lf._rvol({"averageDailyVolume3Month": 4_000_000}) is None
    assert lf._rvol({"regularMarketVolume": 8_000_000,
                     "averageDailyVolume3Month": 0}) is None


def test_mock_mode_runs_nothing(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_MODE", "mock")
    out = lf.screen(force=True)
    assert out["results"] == []
    assert "mock" in out["note"]


def test_describe_carries_the_caveat():
    d = lf.describe()
    assert d["max_float"] == lf.MAX_FLOAT
    # A screen presented without this reads as a signal generator.
    assert "not an edge" in d["caveat"]


def _quote(**kw):
    base = {"symbol": "AAA", "regularMarketPrice": 5.0,
            "regularMarketVolume": 8_000_000, "marketCap": 500_000_000,
            "averageDailyVolume3Month": 2_000_000, "currency": "USD",
            "fullExchangeName": "NasdaqCM"}
    base.update(kw)
    return base


def _run(monkeypatch, quotes, structures, **overrides):
    """Drive screen() with a stubbed market so the filter logic is what's tested."""
    import sys
    import types as _t

    # The suite runs with DATA_MODE=mock, and screen() refuses to run there —
    # so a stubbed market test has to say it is live or it never reaches the
    # filters it is trying to exercise.
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_MODE", "live")

    fake_yf = _t.ModuleType("yfinance")
    fake_yf.screen = lambda src, **kw: {"quotes": quotes}

    class _Q:
        def __init__(self, *a, **k):
            pass
    fake_yf.EquityQuery = _Q
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    from app.services import market_data
    monkeypatch.setattr(
        market_data, "get_market_data",
        lambda s: _t.SimpleNamespace(structure=structures.get(s)))
    lf._CACHE.clear()
    return lf.screen(force=True, **overrides)


def test_a_clean_low_float_runner_passes(monkeypatch):
    out = _run(monkeypatch, [_quote()], {"AAA": {"float_shares": 9_000_000}})
    assert [r["symbol"] for r in out["results"]] == ["AAA"]
    r = out["results"][0]
    assert r["rvol"] == pytest.approx(4.0)
    # The number the screen is actually about: 8M traded on a 9M float.
    assert r["float_turnover"] == pytest.approx(0.89, abs=0.01)


@pytest.mark.parametrize("bad,why", [
    ({"regularMarketPrice": 25.0}, "too expensive"),
    ({"regularMarketVolume": 1_000_000}, "not enough volume"),
    ({"marketCap": 9_000_000_000}, "too big"),
    ({"averageDailyVolume3Month": 8_000_000}, "rvol only 1x"),
])
def test_each_filter_rejects_on_its_own(monkeypatch, bad, why):
    out = _run(monkeypatch, [_quote(**bad)], {"AAA": {"float_shares": 9_000_000}})
    assert out["results"] == [], why


def test_a_float_over_the_ceiling_is_rejected(monkeypatch):
    out = _run(monkeypatch, [_quote()], {"AAA": {"float_shares": 200_000_000}})
    assert out["results"] == []


def test_an_unknown_float_is_excluded_by_default(monkeypatch):
    # Passing a name because the number is missing would quietly turn this into
    # a four-filter screen.
    out = _run(monkeypatch, [_quote()], {"AAA": {}})
    assert out["results"] == []


def test_an_unknown_float_can_be_opted_back_in(monkeypatch):
    import sys
    import types as _t
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_MODE", "live")
    fake_yf = _t.ModuleType("yfinance")
    fake_yf.screen = lambda src, **kw: {"quotes": [_quote()]}
    fake_yf.EquityQuery = type("Q", (), {"__init__": lambda self, *a, **k: None})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    from app.services import market_data
    monkeypatch.setattr(market_data, "get_market_data",
                        lambda s: _t.SimpleNamespace(structure={}))
    lf._CACHE.clear()
    out = lf.screen(force=True, relax_float=True)
    assert [r["symbol"] for r in out["results"]] == ["AAA"]
    assert out["results"][0]["float_unknown"] is True


def test_foreign_listings_are_excluded(monkeypatch):
    # A Hong Kong line with a 2.7bn share float came back on the first live run.
    quotes = [
        _quote(symbol="2477.HK", currency="HKD", fullExchangeName="HKSE"),
        _quote(symbol="BBB.TO", currency="CAD", fullExchangeName="Toronto"),
    ]
    out = _run(monkeypatch, quotes, {"2477.HK": {"float_shares": 1_000_000},
                                     "BBB.TO": {"float_shares": 1_000_000}})
    assert out["results"] == []
