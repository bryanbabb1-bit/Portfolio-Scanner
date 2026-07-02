"""Core backend tests — run entirely on deterministic mock data.

    cd backend && .venv/Scripts/python -m pytest tests -q
"""
import os

os.environ["DATA_MODE"] = "mock"       # must be set before app imports
os.environ["ADVISOR_ENABLED"] = "0"    # never shell out to claude in tests

from app.models.schemas import (  # noqa: E402
    AnalystView, Indicators, Quote, StockReport,
)
from app.routers.breakouts import breakouts  # noqa: E402
from app.routers.insights import get_insights, get_news  # noqa: E402
from app.routers.scan import scan  # noqa: E402
from app.services import insights, market_data, screener  # noqa: E402
from app.services import portfolio as pf_service  # noqa: E402
from app.services.technical import (  # noqa: E402
    build_quote, compute_indicators, derive_signals,
)


def _report(**overrides) -> StockReport:
    """A held report with quiet defaults; tests override what they probe."""
    base = dict(
        symbol="TEST",
        quote=Quote(symbol="TEST", price=100.0, change=1.0, change_pct=1.0,
                    source="mock"),
        indicators=Indicators(rsi=50, sma50=95, sma200=90, trend="uptrend",
                              pct_from_52w_high=-10, volume_ratio=1.0),
        analyst=AnalystView(),
        shares=10, cost_basis=90, market_value=1000.0, unrealized_pl_pct=11.1,
    )
    base.update(overrides)
    return StockReport(**base)


# ---------------------------------------------------------------- technicals
def test_indicators_compute_on_mock_history():
    md = market_data.get_market_data("NVDA")
    ind = compute_indicators(md.history)
    assert ind.rsi is not None and 0 <= ind.rsi <= 100
    assert ind.sma20 and ind.sma50 and ind.sma200
    assert ind.trend in {"uptrend", "downtrend", "sideways"}
    quote = build_quote(md, ind)
    assert quote.price > 0
    assert derive_signals(quote, ind)  # never empty


def test_breakout_score_bounds():
    for sym in ["NVDA", "MSFT", "PLTR", "ZZZZ"]:
        md = market_data.get_market_data(sym)
        cand = screener.evaluate(sym, None, md)
        assert 0 <= cand.score <= 100
        assert cand.thesis


# ----------------------------------------------------------------- portfolio
def test_portfolio_summary_math_consistent():
    summary, reports = pf_service.portfolio_summary()
    assert summary.positions == len(reports)
    assert summary.total_market_value == round(
        sum(r.market_value or 0 for r in reports), 2)
    assert abs(summary.total_unrealized_pl -
               (summary.total_market_value - summary.total_cost)) < 0.01


def test_scan_and_breakout_endpoints():
    s = scan(include_watchlist=True)
    assert s["count"] == len(s["results"]) > 0
    b = breakouts(min_score=0, limit=5)
    assert len(b["results"]) <= 5
    scores = [c.score for c in b["results"]]
    assert scores == sorted(scores, reverse=True)


# ------------------------------------------------------------------ insights
def test_risk_metrics_sane():
    _, reports = pf_service.portfolio_summary()
    risk = insights.compute_risk(reports)
    assert risk.top_symbol is not None
    assert 0 < (risk.top_weight_pct or 0) <= 100
    assert (risk.top5_weight_pct or 0) >= (risk.top_weight_pct or 0)
    assert (risk.max_drawdown_pct or 0) <= 0
    assert (risk.volatility_pct or 0) > 0
    assert risk.best_day_pct is not None and risk.worst_day_pct is not None
    assert risk.best_day_pct >= risk.worst_day_pct


def test_value_series_unions_mismatched_calendars(monkeypatch):
    """Holdings with different trading calendars must be unioned + ffilled,
    not silently truncated to the first symbol's index."""
    import pandas as pd
    from app.services.market_data import MarketData

    base = pd.date_range("2025-01-01", periods=10, freq="B")
    calendars = {"AAA": base[:-1], "BBB": base[1:]}  # BBB has one later day

    def fake_md(symbol):
        idx = calendars[symbol.upper()]
        df = pd.DataFrame(
            {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1},
            index=idx,
        )
        return MarketData(symbol.upper(), symbol, df, {}, [], "mock")

    monkeypatch.setattr(insights.market_data, "get_market_data", fake_md)
    monkeypatch.setattr(insights.pf_service, "load_portfolio", lambda: {
        "holdings": [
            {"symbol": "AAA", "shares": 1, "cost_basis": 1},
            {"symbol": "BBB", "shares": 1, "cost_basis": 1},
        ]
    })

    series = insights._portfolio_value_series()
    # BBB's final day survives even though AAA (first symbol) lacks it,
    # with AAA forward-filled — so the last value is 2.0.
    assert series.index.max() == base[-1]
    assert float(series.iloc[-1]) == 2.0


def test_alert_rules_fire():
    overbought = _report(indicators=Indicators(rsi=80))
    alerts = insights.build_alerts([overbought])
    assert any(a.label == "Overbought" for a in alerts)

    crash = _report(quote=Quote(symbol="TEST", price=100, change=-6,
                                change_pct=-6.0, source="mock"))
    alerts = insights.build_alerts([crash])
    assert any(a.severity == "critical" and a.label == "Sharp drop"
               for a in alerts)

    # 100% weight in one name → concentration warning
    alerts = insights.build_alerts([_report()])
    assert any(a.label == "Concentration risk" for a in alerts)


def test_alerts_sorted_by_severity():
    out = get_insights()
    order = {"critical": 0, "warning": 1, "opportunity": 2}
    ranks = [order[a.severity] for a in out.alerts]
    assert ranks == sorted(ranks)


def test_discovery_excludes_owned_and_sorts():
    from app.services import discovery

    out = discovery.discover(min_score=0, limit=100)
    pf = pf_service.load_portfolio()
    owned = {i["symbol"].upper()
             for i in pf.get("holdings", []) + pf.get("watchlist", [])}
    syms = [c.symbol for c in out["results"]]
    assert syms and not owned.intersection(syms)
    scores = [c.score for c in out["results"]]
    assert scores == sorted(scores, reverse=True)
    # every candidate carries a company name, not a bare ticker
    assert all(c.quote.name and c.quote.name != c.symbol for c in out["results"])


def test_ask_returns_fallback_when_advisor_disabled():
    from app.services import advisor
    out = advisor.ask("portfolio", None, "Should I sell CLSK?")
    assert out["engine"] == "fallback"
    assert out["answer"]


def test_conviction_rules_fire_and_stay_quiet():
    from app.services.conviction import _detect

    quiet = Quote(symbol="T", price=100, change=0.5, change_pct=0.5, source="mock")
    calm = Indicators(rsi=55, sma50=98, sma200=95, trend="uptrend",
                      pct_from_52w_high=-10, volume_ratio=1.0)
    assert _detect("T", calm, quiet, True, 5.0, 50) == []

    # held name oversold right at a rising 200-day -> buy
    dip = Indicators(rsi=30, sma50=101, sma200=99.5, trend="uptrend",
                     pct_from_52w_high=-15, volume_ratio=1.1)
    sigs = _detect("T", dip, quiet, True, -8.0, 40)
    assert any(s["side"] == "buy" and s["rule"] == "oversold-at-support" for s in sigs)

    # blowoff: extreme RSI + volume spike -> sell
    hot = Indicators(rsi=83, sma50=101, sma200=95, trend="uptrend",
                     pct_from_52w_high=-1, volume_ratio=2.5)
    sigs = _detect("T", hot, quiet, True, 40.0, 60)
    assert any(s["side"] == "sell" and s["rule"] == "blowoff-top" for s in sigs)

    # non-held discovery name with top-tier score -> buy
    sigs = _detect("T", calm, quiet, False, None, 76)
    assert any(s["rule"] == "high-conviction-discovery" for s in sigs)

    # held, crashing through a broken trend -> sell
    crash = Quote(symbol="T", price=80, change=-8, change_pct=-9.0, source="mock")
    broken = Indicators(rsi=35, sma50=90, sma200=95, trend="downtrend",
                        pct_from_52w_high=-30, volume_ratio=2.0)
    sigs = _detect("T", broken, crash, True, -25.0, 20)
    assert any(s["rule"] == "trend-break" for s in sigs)
    assert any(s["rule"] == "sharp-breakdown" for s in sigs)


def test_auto_theme_categorization():
    from app.services import themes

    # Seed map covers held + universe names with zero cost.
    assert themes.theme_for("NVDA") == "AI Infrastructure"
    assert themes.theme_for("clsk") == "Compute Power"
    assert themes.theme_for("SGOV") == "Cash & Income"
    assert themes.theme_for("GEV") == "Energy"
    # Manual override always wins.
    assert themes.resolve("NVDA", "Custom") == "Custom"
    # Unknown ticker with the advisor disabled falls back without persisting.
    assert themes.theme_for("ZZZQ") == "Other"
    assert "ZZZQ" not in themes._learned

    # Reports get themes with no manual selection in portfolio.json.
    _, reports = pf_service.portfolio_summary()
    assert all(r.theme for r in reports)
    assert {r.symbol: r.theme for r in reports}["CLSK"] == "Compute Power"


def test_pins_crud(tmp_path, monkeypatch):
    from app.services import pins

    monkeypatch.setattr(pins, "_FILE", tmp_path / "pinned.json")
    p = pins.add("NVDA", "advisor", "Add near $191 while the 200-day holds.")
    assert p["status"] == "open" and p["symbol"] == "NVDA"
    # duplicate pin returns the existing one
    again = pins.add("NVDA", "advisor", "Add near $191 while the 200-day holds.")
    assert again["id"] == p["id"]
    assert len(pins.list_pins()) == 1

    done = pins.update(p["id"], "done")
    assert done["status"] == "done" and done["done_at"]
    assert pins.update("nope", "done") is None
    assert pins.delete(p["id"]) is True
    assert pins.delete(p["id"]) is False
    assert pins.list_pins() == []


def test_news_deduped_and_tagged():
    out = get_news(limit=50)
    titles = [n.title for n in out["results"]]
    assert len(titles) == len(set(titles))
    assert all(n.symbols for n in out["results"])
