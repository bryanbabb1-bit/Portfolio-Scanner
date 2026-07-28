"""Core backend tests — run entirely on deterministic mock data.

    cd backend && .venv/Scripts/python -m pytest tests -q
"""
import os

import pytest

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
    # total = positions + cash (cash counts toward the account value)
    assert summary.total_market_value == round(
        sum(r.market_value or 0 for r in reports) + summary.cash, 2)
    # P/L is on the invested positions only — cash has none
    assert abs(summary.total_unrealized_pl -
               (summary.total_market_value - summary.cash - summary.total_cost)) < 0.01


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
    assert all(a.id for a in out.alerts)  # every alert carries a dismissal key


def test_alert_dismissal_hides_then_resurfaces(tmp_path, monkeypatch):
    import time as _t
    monkeypatch.setattr(insights, "_DISMISS_FILE", tmp_path / "d.json")

    before = get_insights().alerts
    assert before, "need at least one alert to test dismissal"
    target = before[0].id
    insights.dismiss_alert(target)
    after = get_insights().alerts
    assert target not in {a.id for a in after}  # hidden now
    # expired dismissals resurface
    monkeypatch.setattr(insights, "_DISMISS_TTL", -1)
    again = get_insights().alerts
    assert target in {a.id for a in again}


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

    quiet = Quote(symbol="T", price=100, change=0.5, change_pct=0.5, source="live")
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

    # RSI buy zone WITH confirmation (structure intact, not crashing, score
    # ok) — price 7.5% off the 200-day, so oversold-at-support doesn't claim it
    rsi_zone = Indicators(rsi=30, sma50=95, sma200=93, trend="sideways",
                          pct_from_52w_high=-18, volume_ratio=1.0)
    sigs = _detect("T", rsi_zone, quiet, True, -10.0, 40)
    assert any(s["rule"] == "rsi-buy-zone" for s in sigs)
    # ...but NOT when the long-term structure is broken (price far below a
    # collapsed 200-day — no validation, just a falling knife)
    broken_struct = Indicators(rsi=30, sma50=90, sma200=140, trend="downtrend",
                               pct_from_52w_high=-40, volume_ratio=1.0)
    sigs = _detect("T", broken_struct, quiet, True, -40.0, 40)
    assert not any(s["rule"] == "rsi-buy-zone" for s in sigs)

    # RSI sell zone on a held name at the highs. The rule LOGIC still works,
    # but the rule is retired (it lost money on the replay), so it only shows
    # up for the backtest — see tests/test_retirement.py.
    hot75 = Indicators(rsi=76, sma50=101, sma200=95, trend="uptrend",
                       pct_from_52w_high=-1, volume_ratio=1.0)
    sigs = _detect("T", hot75, quiet, True, 30.0, 60, include_retired=True)
    assert any(s["rule"] == "rsi-sell-zone" for s in sigs)
    assert not any(s["rule"] == "rsi-sell-zone"
                   for s in _detect("T", hot75, quiet, True, 30.0, 60))

    # RSI reclaim: crossed up through 45 after a washout, structure intact
    reclaim = Indicators(rsi=46, rsi_prev=43, rsi_min_10d=29, sma50=98,
                         sma200=100, trend="sideways",
                         pct_from_52w_high=-15, volume_ratio=1.1)
    sigs = _detect("T", reclaim, quiet, True, -12.0, 45)
    assert any(s["rule"] == "rsi-reclaim" for s in sigs)
    # no reclaim signal without the prior washout (RSI never got stretched)
    drift = Indicators(rsi=46, rsi_prev=43, rsi_min_10d=41, sma50=98,
                       sma200=100, trend="sideways",
                       pct_from_52w_high=-15, volume_ratio=1.1)
    sigs = _detect("T", drift, quiet, True, -12.0, 45)
    assert not any(s["rule"] == "rsi-reclaim" for s in sigs)

    # earnings gate: NO buy slaps 0-2 days before a report; sells still fire
    dip2 = Indicators(rsi=30, sma50=95, sma200=93, trend="sideways",
                      pct_from_52w_high=-18, volume_ratio=1.0)
    assert not any(s["side"] == "buy"
                   for s in _detect("T", dip2, quiet, True, -10.0, 40, earn_days=1))
    crash2 = Quote(symbol="T", price=80, change=-8, change_pct=-9.0, source="live")
    broken2 = Indicators(rsi=35, sma50=90, sma200=95, trend="downtrend",
                         pct_from_52w_high=-30, volume_ratio=2.0)
    # include_retired: this asserts the EARNINGS GATE (buys blocked, sells not),
    # and the sell rules that fit this setup are retired from firing live.
    assert any(s["side"] == "sell"
               for s in _detect("T", broken2, crash2, True, -25.0, 20,
                                earn_days=1, include_retired=True))

    # momentum ignition: already ripping on volume near highs (the SNDK case)
    ripping = Quote(symbol="T", price=100, change=6, change_pct=6.4, source="live")
    ignite = Indicators(rsi=68, sma50=85, sma200=70, trend="uptrend",
                        pct_from_52w_high=-2, volume_ratio=2.4,
                        ret_5d_pct=18.0, ret_20d_pct=42.0)
    sigs = _detect("T", ignite, ripping, False, None, 65)
    assert any(s["rule"] == "momentum-ignition" for s in sigs)
    # a quiet grind up (no volume, modest 5d) stays silent
    grind = Indicators(rsi=60, sma50=85, sma200=70, trend="uptrend",
                       pct_from_52w_high=-4, volume_ratio=1.0,
                       ret_5d_pct=4.0, ret_20d_pct=12.0)
    assert not any(s["rule"] == "momentum-ignition"
                   for s in _detect("T", grind, quiet, False, None, 55))

    # uptrend name pulled back into the accumulation zone -> quality dip buy
    dip_zone = Indicators(rsi=36, sma50=102, sma200=95, trend="uptrend",
                          pct_from_52w_high=-12, volume_ratio=1.0)
    sigs = _detect("T", dip_zone, quiet, False, None, 50)
    assert any(s["rule"] == "quality-dip" for s in sigs)

    # deeply oversold, bouncing hard on volume -> washed-out reversal buy
    bounce = Quote(symbol="T", price=70, change=2.1, change_pct=3.1, source="live")
    washed = Indicators(rsi=27, sma50=80, sma200=90, trend="downtrend",
                        pct_from_52w_high=-40, volume_ratio=2.2)
    sigs = _detect("T", washed, bounce, True, -30.0, 25)
    assert any(s["rule"] == "washed-out-reversal" for s in sigs)

    # held, crashing through a broken trend -> sell. Both of these rules are
    # RETIRED (they lost money on the replay), so the logic is asserted with
    # include_retired and the live suppression is asserted right after.
    crash = Quote(symbol="T", price=80, change=-8, change_pct=-9.0, source="live")
    broken = Indicators(rsi=35, sma50=90, sma200=95, trend="downtrend",
                        pct_from_52w_high=-30, volume_ratio=2.0)
    sigs = _detect("T", broken, crash, True, -25.0, 20, include_retired=True)
    assert any(s["rule"] == "trend-break" for s in sigs)
    assert any(s["rule"] == "sharp-breakdown" for s in sigs)
    assert not _detect("T", broken, crash, True, -25.0, 20)


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


def test_watchdog_sleeps_when_market_closed(tmp_path, monkeypatch):
    import json as _json
    from app.services import conviction

    notes = tmp_path / "notes.json"
    now = __import__("time").time()
    notes.write_text(_json.dumps({
        "AAA:rule:2026-07-06": {"id": "AAA:rule:2026-07-06", "symbol": "AAA",
                                "side": "buy", "ts": now},
    }))
    monkeypatch.setattr(conviction, "_NOTES_FILE", notes)
    monkeypatch.setattr(conviction, "market_open", lambda: False)
    # closed: returns the existing active signal, runs no detection/push
    fired = {"pushed": False}
    monkeypatch.setattr(conviction, "_load",
                        lambda p: _json.loads(notes.read_text()) if str(p) == str(notes) else {})
    out = conviction.scan()
    assert [s["symbol"] for s in out] == ["AAA"]


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


def test_advisor_consistency_memory(tmp_path, monkeypatch):
    from app.models.schemas import AdvisorNote
    from app.services import advisor

    monkeypatch.setattr(advisor, "_HISTORY_FILE", tmp_path / "hist.json")
    monkeypatch.setattr(advisor, "_history", {})

    note = AdvisorNote(
        symbol="PORTFOLIO", persona="p", engine="claude",
        generated_at="2026-07-02 10:00:00",
        summary="De-risking is complete.",
        insights=[], risks=["CRWD gap risk"],
        actions=["Do not chase CRWD (RSI 71.7) — wait for a pullback toward RSI 60."],
    )
    advisor._remember_history("portfolio:brief", note)

    block = advisor._prior_advice_block("portfolio:brief")
    assert "CONSISTENCY RULE" in block and "Do not chase CRWD" in block

    # a per-stock CRWD note must see the portfolio brief's stance on CRWD
    stock_block = advisor._prior_advice_block("stock:CRWD", "CRWD")
    assert "Do not chase CRWD" in stock_block

    # fallback notes are never stored as prior advice
    fb = AdvisorNote(symbol="X", persona="p", engine="fallback",
                     generated_at="t", summary="s")
    advisor._remember_history("stock:X", fb)
    assert advisor._prior_advice_block("stock:X") == ""

    # capped at the last three notes per context
    for k in range(5):
        advisor._remember_history("portfolio:brief", note)
    assert len(advisor._history["portfolio:brief"]) == 3


def test_strategy_persistence_and_gating(tmp_path, monkeypatch):
    from app.services import strategy

    monkeypatch.setattr(strategy, "_FILE", tmp_path / "strategy.json")
    assert strategy.load() is None
    assert strategy.facts_block() == ""  # nothing yet

    doc = strategy.save({
        "goals": {"target_value": 50000, "horizon": "5 years",
                  "monthly_contribution": 500, "risk_appetite": "balanced"},
        "thesis": "Compound AI infrastructure exposure with disciplined cash.",
        "short_term": ["Redeploy $300/week into dips"],
        "long_term": ["Build NVDA to a 10% core position"],
        "allocation_targets": {"AI Infrastructure": 30, "Cash & Income": 20},
        "guardrails": ["No single position above 15%"],
        "milestones": ["$15k by 2026-12-31"],
        "approved": False,
    })
    assert doc["updated_at"]
    # drafts are NOT injected into briefs — only approved plans are
    assert strategy.facts_block() == ""
    strategy.save({**doc, "approved": True})
    block = strategy.facts_block()
    assert "AGREED STRATEGY" in block
    assert "grow to $50,000" in block and "AI Infrastructure 30%" in block


def test_watchpoints_arm_trigger_journal(tmp_path, monkeypatch):
    from app.services import journal, watchpoints

    monkeypatch.setattr(watchpoints, "_FILE", tmp_path / "wp.json")
    monkeypatch.setattr(journal, "_JOURNAL_FILE", tmp_path / "j.json")

    wp = watchpoints.add("IREN", "price_below", 38.80,
                         note="Sell half (~$670) on a close below this week's low")
    assert wp["status"] == "armed" and wp["side"] == "buy"  # inferred default
    # identical armed condition dedupes
    again = watchpoints.add("IREN", "price_below", 38.80)
    assert again["id"] == wp["id"]

    # above the level: nothing fires
    assert watchpoints.check({"IREN": (40.0, 45.0)}) == []
    # at/below the level: fires a slap-ready signal, marks triggered, journals
    fired = watchpoints.check({"IREN": (38.5, 33.0)})
    assert len(fired) == 1
    sig = fired[0]
    assert sig["rule"] == "watchpoint" and sig["symbol"] == "IREN"
    assert "Sell half" in sig["what"]
    assert watchpoints.list_watchpoints()[0]["status"] == "triggered"
    # journaled as an ALERT (not an executed trade) so the advisor can't misread it
    assert any("ALERT (not executed)" in e["note"] for e in journal.list_entries())
    # triggered watchpoints never fire twice
    assert watchpoints.check({"IREN": (30.0, 20.0)}) == []

    # rsi_above semantics (the 'reclaim 45' style)
    watchpoints.add("AVGO", "rsi_above", 45, note="Start the position")
    assert watchpoints.check({"AVGO": (360.0, 44.0)}, close_window=False) == []
    assert len(watchpoints.check({"AVGO": (365.0, 46.2)}, close_window=False)) == 1

    # confirm='close' only evaluates inside the close window
    watchpoints.add("CIFR", "price_below", 17, note="Exit fully",
                    confirm="close")
    assert watchpoints.check({"CIFR": (16.5, 40.0)}, close_window=False) == []
    assert len(watchpoints.check({"CIFR": (16.5, 40.0)}, close_window=True)) == 1


def test_scorecard_grades_signals(tmp_path, monkeypatch):
    from app.services import scorecard

    monkeypatch.setattr(scorecard, "_FILE", tmp_path / "hist.json")
    scorecard.record({"id": "a", "symbol": "AAA", "side": "buy",
                      "rule": "momentum-ignition", "price": 100.0, "ts": 1.0})
    scorecard.record({"id": "a", "symbol": "AAA", "side": "buy",
                      "rule": "momentum-ignition", "price": 100.0, "ts": 1.0})  # dedupe
    scorecard.record({"id": "b", "symbol": "BBB", "side": "sell",
                      "rule": "trend-break", "price": 50.0, "ts": 2.0})

    prices = {"AAA": 110.0, "BBB": 45.0}  # buy +10%, sell -10% (both wins)
    card = scorecard.compute(price_of=lambda s: prices.get(s))
    assert card["count"] == 2
    assert card["overall_win_rate"] == 100
    by_rule = {r["rule"]: r for r in card["rules"]}
    assert by_rule["momentum-ignition"]["avg_effective_pct"] == 10.0
    assert by_rule["trend-break"]["avg_effective_pct"] == 10.0  # sign-adjusted


def test_runner_radar_scores_low_float_higher():
    from app.services import runner

    out = runner.radar(min_score=0, limit=100)
    assert out["results"] and out["universe"] > 0
    scores = [c.runner_score for c in out["results"]]
    assert scores == sorted(scores, reverse=True)
    # every candidate carries structural DNA and a caution
    for c in out["results"]:
        assert 0 <= c.runner_score <= 100
        assert c.stage in {"coiled", "igniting", "extended", "cooling"}
        assert c.caution
    # the seeded low-float runners should outscore a large-cap by structure
    by_sym = {c.symbol: c for c in out["results"]}
    if "MGRT" in by_sym and "VRT" in by_sym:
        assert by_sym["MGRT"].runner_score > by_sym["VRT"].runner_score
        assert by_sym["MGRT"].float_shares < by_sym["VRT"].float_shares


def test_runner_clean_rows_and_ignition_bar(monkeypatch):
    from app.services import runner

    raw = [
        {"symbol": "GOOD", "shortName": "Good Co", "marketCap": 800e6,
         "regularMarketPrice": 12.0, "regularMarketVolume": 5e6,
         "regularMarketChangePercent": 34.0},
        {"symbol": "2295.HK", "marketCap": 1e9, "regularMarketPrice": 5,
         "regularMarketVolume": 2e6, "regularMarketChangePercent": 40},  # foreign
        {"symbol": "SHELL", "marketCap": 200_000, "regularMarketPrice": 0.4,
         "regularMarketVolume": 9e6, "regularMarketChangePercent": 120},  # nano shell
        {"symbol": "MEGA", "marketCap": 50e9, "regularMarketPrice": 300,
         "regularMarketVolume": 8e6, "regularMarketChangePercent": 12},   # too big
        {"symbol": "THIN", "marketCap": 600e6, "regularMarketPrice": 8,
         "regularMarketVolume": 200_000, "regularMarketChangePercent": 30},  # low vol
    ]
    cleaned = runner._clean_rows(raw)
    assert [r["symbol"] for r in cleaned] == ["GOOD"]

    # staged ignition: catch EARLY movers on heavy volume first; flag the
    # already-run name as extended; drop noise + oversized.
    monkeypatch.setattr(runner, "live_movers", lambda force=False: [
        {"symbol": "EARLY", "name": "Early", "change_pct": 12.0, "market_cap": 900e6,
         "price": 6.0, "volume": 4e6, "rvol": 6.0, "range_pos": 0.9},   # igniting
        {"symbol": "TOPPED", "name": "Topped", "change_pct": 42.0, "market_cap": 900e6,
         "price": 6.0, "volume": 4e6, "rvol": 5.0, "range_pos": 0.8},   # extended
        {"symbol": "NOISE", "name": "Noise", "change_pct": 9.0, "market_cap": 900e6,
         "price": 6.0, "volume": 4e6, "rvol": 1.1, "range_pos": 0.7},   # low rvol -> drop
        {"symbol": "BIG", "name": "Big", "change_pct": 30.0, "market_cap": 9e9,
         "price": 6.0, "volume": 4e6, "rvol": 8.0, "range_pos": 0.9},   # too big
    ])
    hot = runner.igniting_movers()
    assert [m["symbol"] for m in hot] == ["EARLY", "TOPPED"]   # igniting before extended
    assert hot[0]["stage"] == "igniting" and hot[1]["stage"] == "extended"


def test_push_token_registration(tmp_path, monkeypatch):
    from app.services import push

    monkeypatch.setattr(push, "_FILE", tmp_path / "tok.json")
    with pytest.raises(ValueError):
        push.register("not-a-real-token")
    e = push.register("ExponentPushToken[abc123]", "ios")
    assert e["platform"] == "ios"
    # idempotent
    push.register("ExponentPushToken[abc123]")
    assert push.tokens() == ["ExponentPushToken[abc123]"]
    # no devices -> send is a no-op, never raises
    monkeypatch.setattr(push, "_FILE", tmp_path / "empty.json")
    assert push.send("t", "b")["sent"] == 0
    assert push.unregister("ExponentPushToken[abc123]") is False


def test_news_deduped_and_tagged():
    out = get_news(limit=50)
    titles = [n.title for n in out["results"]]
    assert len(titles) == len(set(titles))
    assert all(n.symbols for n in out["results"])


def test_stance_ledger_consistency(tmp_path, monkeypatch):
    """The stance ledger is the advisor's memory — one call per symbol that
    every surface reads and stays consistent with."""
    from app.services import stance
    monkeypatch.setattr(stance, "_FILE", tmp_path / "stances.json")
    assert stance.get("NVDA") is None
    stance.set_stance("nvda", "hold", headline="steady", thesis="thesis intact",
                      target="$210", stop="$190", price=195.0)
    s = stance.get("NVDA")
    assert s["action"] == "HOLD" and s["symbol"] == "NVDA"
    block = stance.block("NVDA")
    assert "STANDING CALL on NVDA" in block and "Do NOT change the call" in block
    # an immaterial move is spelled out and the call is held; a big move isn't
    held = stance.block("NVDA", 195.5)
    assert "IMMATERIAL" in held
    assert stance.is_stable("NVDA", 195.5) and not stance.is_stable("NVDA", 260.0)
    # garbage normalizes to HOLD, prev_action is tracked across changes
    stance.set_stance("NVDA", "not-a-call")
    assert stance.get("NVDA")["action"] == "HOLD"
    stance.set_stance("NVDA", "SELL")
    assert stance.get("NVDA")["prev_action"] == "HOLD"
    assert "NVDA" in stance.book_block(["NVDA", "AAPL"])


def test_planwatch_level_parse():
    from app.services import planwatch
    assert planwatch._level_in("Trim IREN near $672 into strength") == 672.0
    assert planwatch._level_in("no dollar level here") is None


def test_planwatch_baseline_then_holds(tmp_path, monkeypatch):
    """First sighting of a staged plan sets its baseline (no fire); with the
    advisor off a moved plan re-evaluates to 'holds' and fires nothing."""
    from app.services import planwatch, pins
    patched: dict = {}
    monkeypatch.setattr(pins, "patch", lambda pid, **f: patched.update(f))
    # no baseline yet -> baseline is set, nothing fires
    monkeypatch.setattr(pins, "list_pins", lambda: [
        {"id": "p1", "status": "open", "symbol": "IREN",
         "text": "Sell IREN as loss control"}])
    assert planwatch.check({"IREN": 10.0}) == []
    assert patched.get("price_at_pin") == 10.0
    # has baseline, big move, advisor disabled -> reevaluate 'holds' -> no signal
    monkeypatch.setattr(pins, "list_pins", lambda: [
        {"id": "p2", "status": "open", "symbol": "IREN",
         "text": "Sell IREN near $672", "price_at_pin": 10.0}])
    assert planwatch.check({"IREN": 13.0}) == []


def test_cash_counts_toward_total_and_allocation(monkeypatch):
    """Uninvested cash adds to the account total and the Cash & Income bucket,
    but is never treated as a position."""
    from app.services import portfolio as pf
    real = pf.load_portfolio()
    monkeypatch.setattr(pf, "load_portfolio", lambda: {**real, "cash": 1000.0})
    summary, reports = pf.portfolio_summary()
    positions = sum(r.market_value or 0 for r in reports)
    assert abs(summary.total_market_value - (positions + 1000.0)) < 0.01
    assert summary.cash == 1000.0
    assert summary.positions == len(reports)          # cash is not a position
    assert summary.by_theme.get("Cash & Income", 0) >= 1000.0


def test_watchpoint_no_rearm_after_trigger(tmp_path, monkeypatch):
    """A fired watchpoint must not be re-armed with an identical condition —
    that caused the same alert to fire every scan ('got it 5 times today')."""
    from app.services import watchpoints as wp
    monkeypatch.setattr(wp, "_FILE", tmp_path / "wp.json")
    a = wp.add("AVGO", "rsi_above", 45.0, note="buy when rsi reclaims 45")
    fired = wp.check({"AVGO": (375.0, 46.0)})           # crosses -> fires once
    assert len(fired) == 1
    assert wp.list_watchpoints()[0]["status"] == "triggered"
    # re-arming the same (already-true) condition returns the existing one
    b = wp.add("AVGO", "rsi_above", 45.0, note="buy when rsi reclaims 45")
    assert b["id"] == a["id"]
    assert len([w for w in wp.list_watchpoints() if w["symbol"] == "AVGO"]) == 1
    assert wp.check({"AVGO": (375.0, 46.0)}) == []       # and never re-fires


def test_watchpoint_dismiss_blocks_advisor_rearm(tmp_path, monkeypatch):
    """Deleting a game-plan watchpoint must stick — the advisor's brief can't
    re-arm it ('AVGO keeps popping back up'), but a manual re-add revives it."""
    from app.services import watchpoints as wp
    monkeypatch.setattr(wp, "_FILE", tmp_path / "wp.json")
    a = wp.add("AVGO", "rsi_above", 45.0, source="advisor")
    assert wp.delete(a["id"]) is True
    assert wp.list_watchpoints() == []                    # gone from the list
    b = wp.add("AVGO", "rsi_above", 45.0, source="advisor")  # brief tries again
    assert b["status"] == "dismissed"                     # suppressed
    assert wp.list_watchpoints() == []
    c = wp.add("AVGO", "rsi_above", 45.0, source="manual")   # user re-adds
    assert c["status"] == "armed"
    assert len(wp.list_watchpoints()) == 1


def test_runner_stage_classifies_early_vs_extended():
    """The radar must catch ignition EARLY and flag the exhausted top as
    'don't chase' — not slap BUY at +34%."""
    from app.services import runner
    # up 12% on 5x volume, pinned near the day high -> buyable ignition
    assert runner._stage({"change_pct": 12, "rvol": 5.0, "range_pos": 0.9}) == "igniting"
    # up 34% -> the bulk of the move is done, do not chase
    assert runner._stage({"change_pct": 34, "rvol": 6.0, "range_pos": 0.8}) == "extended"
    # up 15% but faded to the bottom of the range -> extended
    assert runner._stage({"change_pct": 15, "rvol": 4.0, "range_pos": 0.2}) == "extended"
    # a small pop on ordinary volume is noise, not a runner
    assert runner._stage({"change_pct": 9, "rvol": 1.2, "range_pos": 0.7}) is None
    # below the ignition floor
    assert runner._stage({"change_pct": 4, "rvol": 10, "range_pos": 1.0}) is None


def test_push_gating_actions_only():
    """Only concrete actions (or your own armed watchpoint) buzz the phone;
    HOLD / AVOID / 'don't chase' stay silent in-app."""
    from app.services.conviction import _should_push
    assert _should_push({"rule": "watchpoint", "action": "HOLD"})          # your trigger
    assert _should_push({"rule": "high-conviction-discovery", "action": "BUY"})
    assert _should_push({"action": "SELL"})
    assert _should_push({"action": "TRIM"})
    assert not _should_push({"rule": "runner-ignition", "action": "AVOID"})  # extended
    assert not _should_push({"action": "HOLD"})
    assert not _should_push({"action": "WATCH"})
    assert not _should_push({"action": None})
