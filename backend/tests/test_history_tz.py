"""One bad symbol must not take the whole chart down.

BRK.B failed its live fetch (Yahoo spells it BRK-B), degraded to mock, and the
mock series carried a tz-naive index. pandas then refused to concat it with the
tz-aware live series, so portfolio_history raised and the endpoint 502'd —
losing the ENTIRE chart because of one ticker.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import market_data, portfolio as pf


def test_class_shares_are_spelled_the_way_yahoo_spells_them():
    assert market_data.yf_symbol("BRK.B") == "BRK-B"
    assert market_data.yf_symbol("BF.B") == "BF-B"
    assert market_data.yf_symbol("brk.b") == "BRK-B"
    # Ordinary tickers pass through untouched.
    assert market_data.yf_symbol("NVDA") == "NVDA"
    assert market_data.yf_symbol(" aapl ") == "AAPL"


def _frame(tz: str | None, n: int = 30, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2026-06-01", periods=n, freq="B", tz=tz)
    return pd.DataFrame({"Open": price, "High": price, "Low": price,
                         "Close": price, "Volume": 1_000}, index=idx)


def test_a_tz_naive_symbol_does_not_break_the_history(monkeypatch):
    """A mock (naive) holding mixed with live (aware) ones must still chart."""
    frames = {
        "AAA": _frame("America/New_York", price=100.0),   # live
        "BBB": _frame(None, price=50.0),                  # degraded to mock
    }

    monkeypatch.setattr(pf, "load_portfolio", lambda: {
        "holdings": [{"symbol": "AAA", "shares": 1, "cost_basis": 90},
                     {"symbol": "BBB", "shares": 2, "cost_basis": 40}],
        "cash": 0,
    })

    class _MD:
        def __init__(self, sym):
            self.symbol = sym
            self.history = frames[sym]
            self.source = "live" if sym == "AAA" else "mock"
            self.live_price = None

    monkeypatch.setattr(pf.market_data, "get_market_data", lambda s: _MD(s))
    monkeypatch.setattr(pf.market_data, "warm_cache", lambda *a, **k: None)
    # Benchmark off — this test is about the holdings concat.
    monkeypatch.setattr(pf, "_benchmark_series", lambda *a, **k: [])

    hist = pf.portfolio_history("6mo")
    assert hist.points, "the chart must survive a tz-naive holding"
    # Both holdings contribute: 1 x 100 + 2 x 50.
    assert hist.points[-1].value == pytest.approx(200.0)


def test_all_naive_still_works(monkeypatch):
    frames = {"AAA": _frame(None, price=10.0)}
    monkeypatch.setattr(pf, "load_portfolio", lambda: {
        "holdings": [{"symbol": "AAA", "shares": 3, "cost_basis": 8}], "cash": 5,
    })

    class _MD:
        def __init__(self, sym):
            self.symbol, self.history, self.source = sym, frames[sym], "mock"
            self.live_price = None

    monkeypatch.setattr(pf.market_data, "get_market_data", lambda s: _MD(s))
    monkeypatch.setattr(pf.market_data, "warm_cache", lambda *a, **k: None)
    monkeypatch.setattr(pf, "_benchmark_series", lambda *a, **k: [])

    hist = pf.portfolio_history("6mo")
    assert hist.points[-1].value == pytest.approx(35.0)   # 3 x 10 + 5 cash
