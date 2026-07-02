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
    sigs = _detect("T", calm, quiet, False, None, 73)
    assert any(s["rule"] == "high-conviction-discovery" for s in sigs)

    # uptrend name pulled back into the accumulation zone -> quality dip buy
    dip_zone = Indicators(rsi=36, sma50=102, sma200=95, trend="uptrend",
                          pct_from_52w_high=-12, volume_ratio=1.0)
    sigs = _detect("T", dip_zone, quiet, False, None, 50)
    assert any(s["rule"] == "quality-dip" for s in sigs)

    # deeply oversold, bouncing hard on volume -> washed-out reversal buy
    bounce = Quote(symbol="T", price=70, change=2.1, change_pct=3.1, source="mock")
    washed = Indicators(rsi=27, sma50=80, sma200=90, trend="downtrend",
                        pct_from_52w_high=-40, volume_ratio=2.2)
    sigs = _detect("T", washed, bounce, True, -30.0, 25)
    assert any(s["rule"] == "washed-out-reversal" for s in sigs)

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

    # Reports get themes with no manual selection in portfolio.json —
    # data-independent: holdings change as Bryan trades.
    _, reports = pf_service.portfolio_summary()
    assert reports and all(r.theme for r in reports)


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


def test_intraday_chart_ranges():
    # per-stock: 1d = 5-min bars with times; 5d = 30-min bars across 5 days
    day = pf_service.price_history("NVDA", "1d")
    assert day.range == "1d" and len(day.candles) >= 30
    assert ":" in day.candles[0].date  # intraday timestamps, not bare dates
    week = pf_service.price_history("NVDA", "5d")
    assert len({c.date[:10] for c in week.candles}) == 5

    # portfolio value intraday aggregates all holdings on a shared clock
    pf_day = pf_service.portfolio_history("1d")
    assert len(pf_day.points) >= 30 and ":" in pf_day.points[0].date
    assert all(p.value > 0 for p in pf_day.points)


def test_journal_diff_detects_trades(tmp_path, monkeypatch):
    from app.services import journal

    monkeypatch.setattr(journal, "_JOURNAL_FILE", tmp_path / "j.json")
    monkeypatch.setattr(journal, "_SNAPSHOT_FILE", tmp_path / "s.json")

    # first run records the baseline silently
    assert journal.snapshot_and_diff(
        [{"symbol": "AAA", "shares": 10}, {"symbol": "BBB", "shares": 5}]) == []
    # trim AAA, close BBB, open CCC
    entries = journal.snapshot_and_diff(
        [{"symbol": "AAA", "shares": 6}, {"symbol": "CCC", "shares": 3}])
    acts = {(e["symbol"], e["action"]) for e in entries}
    assert acts == {("AAA", "sell"), ("BBB", "sell"), ("CCC", "buy")}
    assert all(e["shares"] for e in entries)
    # unchanged holdings journal nothing
    assert journal.snapshot_and_diff(
        [{"symbol": "AAA", "shares": 6}, {"symbol": "CCC", "shares": 3}]) == []
    assert "ALREADY TAKEN" in journal.facts_block()


def test_journal_crud(tmp_path, monkeypatch):
    from app.services import journal

    monkeypatch.setattr(journal, "_JOURNAL_FILE", tmp_path / "j.json")
    e = journal.add_entry("MU", "buy", "Robinhood fill", shares=0.5,
                          price=1010.0, date="2026-06-30", source="manual")
    assert e["action"] == "buy" and e["date"] == "2026-06-30" and e["price"] == 1010.0

    upd = journal.update_entry(e["id"], {"action": "sell", "shares": 0.25,
                                         "symbol": "mu"})
    assert upd["action"] == "sell" and upd["shares"] == 0.25 and upd["symbol"] == "MU"
    assert journal.update_entry("nope", {"note": "x"}) is None
    assert journal.delete_entry(e["id"]) is True
    assert journal.delete_entry(e["id"]) is False

    # legacy entries (old free-text actions) migrate to the structured shape
    import json
    (tmp_path / "j.json").write_text(json.dumps([
        {"id": "old1", "symbol": "CLSK", "action": "sold",
         "detail": "Closed the position entirely", "source": "auto",
         "date": "2026-07-02 08:00", "ts": 1.0}
    ]))
    migrated = journal.list_entries(days=3650)
    assert migrated[0]["action"] == "sell"
    assert migrated[0]["note"] == "Closed the position entirely"
    assert migrated[0]["date"] == "2026-07-02"


def test_signal_dismissal(tmp_path, monkeypatch):
    import json as _json
    from app.services import conviction

    notes_file = tmp_path / "notes.json"
    notes_file.write_text(_json.dumps({
        "AAA:rule:2026-07-02": {"id": "AAA:rule:2026-07-02", "ts": 1.0},
        "BBB:rule:2026-07-02": {"id": "BBB:rule:2026-07-02", "ts": 2.0},
    }))
    monkeypatch.setattr(conviction, "_NOTES_FILE", notes_file)

    assert conviction.dismiss("AAA:rule:2026-07-02") == 1
    saved = _json.loads(notes_file.read_text())
    assert saved["AAA:rule:2026-07-02"]["dismissed"] is True
    assert not saved["BBB:rule:2026-07-02"].get("dismissed")
    # dismiss-all covers the rest; re-dismissing changes nothing
    assert conviction.dismiss() == 1
    assert conviction.dismiss() == 0


def test_news_deduped_and_tagged():
    out = get_news(limit=50)
    titles = [n.title for n in out["results"]]
    assert len(titles) == len(set(titles))
    assert all(n.symbols for n in out["results"])
