"""Backtest tests — the important one is the anti-drift test.

    cd backend && .venv/Scripts/python -m pytest tests/test_backtest.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services import backtest, conviction, market_data, screener, technical  # noqa: E402


def _series(closes, volumes=None) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.Series(closes, index=idx, dtype=float)
    vol = pd.Series(volumes if volumes is not None else [1_000_000] * n,
                    index=idx, dtype=float)
    return pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": vol,
    })


# ------------------------------------------------- indicator_frame contract
def test_frame_matches_scalar_indicators_on_the_last_bar():
    """indicator_frame is only trustworthy if its last row equals what the
    LIVE compute_indicators would say — that equality is the whole basis for
    replaying production rules against it."""
    md = market_data.get_market_data("NVDA")
    df = md.history
    scalar = technical.compute_indicators(df)
    frame = technical.indicator_frame(df)
    last = frame.iloc[-1]

    for field in ("rsi", "sma20", "sma50", "sma200", "macd", "macd_signal",
                  "atr", "bb_upper", "bb_lower", "volume_ratio",
                  "ret_5d_pct", "ret_20d_pct", "pct_from_52w_high"):
        want = getattr(scalar, field)
        got = last[field]
        if want is None:
            continue
        assert abs(float(got) - float(want)) < 0.01, f"{field}: {got} != {want}"
    assert last["trend"] == scalar.trend


def test_frame_is_causal_no_lookahead():
    """Truncating the input must not change earlier rows. If it does, some
    column is peeking at the future and every backtest number is fiction."""
    md = market_data.get_market_data("NVDA")
    df = md.history
    full = technical.indicator_frame(df)
    cut = technical.indicator_frame(df.iloc[:-60])

    tail = cut.index[-1]
    for field in ("rsi", "sma200", "high_52w", "pct_from_52w_high", "volume_ratio"):
        a, b = full.loc[tail, field], cut.loc[tail, field]
        if pd.isna(a) and pd.isna(b):
            continue
        assert abs(float(a) - float(b)) < 1e-6, f"{field} leaked future data"


def test_52w_high_is_trailing_not_global():
    """A rising series then a crash: at the crash bar the trailing high must be
    the recent peak, and pct_from_52w_high must be negative."""
    closes = list(np.linspace(100, 200, 300)) + [120] * 10
    frame = technical.indicator_frame(_series(closes))
    assert frame["high_52w"].iloc[-1] >= 199
    assert frame["pct_from_52w_high"].iloc[-1] < -30


# -------------------------------------------------------- the shim contract
def test_shim_exposes_every_field_the_rules_read():
    """_row_shim must carry every Indicators attribute _detect touches, or a
    rule silently never fires in the backtest."""
    frame = technical.indicator_frame(_series(list(np.linspace(50, 150, 400))))
    ind, quote = backtest._row_shim(frame.iloc[-1].to_dict())
    for field in backtest._IND_FIELDS:
        assert hasattr(ind, field), f"shim missing {field}"
    assert quote.source == "live"     # else _detect suppresses every signal
    assert quote.price is not None


def test_shim_converts_nan_to_none():
    """Early bars have NaN indicators; the rules compare against None, not NaN
    (NaN comparisons are all False and would silently disable rules)."""
    frame = technical.indicator_frame(_series(list(np.linspace(100, 110, 30))))
    ind, _ = backtest._row_shim(frame.iloc[0].to_dict())
    assert ind.sma200 is None
    assert ind.rsi is None or isinstance(ind.rsi, float)


def test_shim_row_is_accepted_by_the_live_rule_engine():
    """The anti-drift guarantee: a shimmed row goes straight into the real
    _detect and the real breakout_score without adaptation."""
    frame = technical.indicator_frame(_series(list(np.linspace(50, 150, 400))))
    ind, quote = backtest._row_shim(frame.iloc[-1].to_dict())
    score = screener.breakout_score(ind, quote)
    assert 0 <= score <= 100
    sigs = conviction._detect("TEST", ind, quote, True, None, score)
    assert isinstance(sigs, list)
    for s in sigs:
        assert {"symbol", "side", "rule", "label"} <= set(s)


def test_a_known_setup_fires_the_expected_rule(monkeypatch):
    """A hand-built washout: deeply oversold, then a bounce on heavy volume.
    That is exactly `washed-out-reversal`, so the replay must find it."""
    up = list(np.linspace(100, 160, 260))       # long uptrend -> sma200 valid
    down = list(np.linspace(160, 96, 40))       # sharp selloff -> RSI <= 30
    closes = up + down + [102.0]                # +6% bounce day
    vols = [1_000_000] * (len(closes) - 1) + [3_000_000]   # 3x volume
    df = _series(closes, vols)

    monkeypatch.setattr(backtest, "WARMUP", 200)
    monkeypatch.setattr(backtest, "HORIZONS", (1,))
    monkeypatch.setattr(backtest, "GRADE_AT", 1)
    monkeypatch.setattr(
        market_data, "get_deep_history",
        lambda sym, years=5: type("MD", (), {"history": pd.concat([df, df.tail(3)])})(),
    )
    sigs = backtest.replay_symbol("TEST", held=True, years=5)
    assert any(s["rule"] == "washed-out-reversal" for s in sigs), \
        [s["rule"] for s in sigs]


# ------------------------------------------------------------- aggregation
def _sig(rule, side, eff20, eff5=0.0, eff60=0.0, mae=-3.0, sym="AAA"):
    return {"symbol": sym, "date": "2024-01-01", "rule": rule, "side": side,
            "price": 100.0, "score": 50.0, "bar": 1,
            "eff_5": eff5, "eff_20": eff20, "eff_60": eff60,
            "fwd_5": eff5, "fwd_20": eff20, "fwd_60": eff60, "mae_pct": mae}


def test_rule_stats_win_rate_and_profit_factor():
    sigs = [_sig("r1", "buy", 10), _sig("r1", "buy", 10),
            _sig("r1", "buy", -5), _sig("r1", "buy", -5)]
    s = backtest._rule_stats(sigs)[0]
    assert s["signals"] == 4
    assert s["win_rate"] == 50.0
    assert s["profit_factor"] == 2.0        # 20 won / 10 lost
    assert s["avg_20"] == 2.5


def test_profit_factor_is_none_when_nothing_lost():
    """No losses means the ratio is undefined, not infinite — never print inf."""
    s = backtest._rule_stats([_sig("r1", "buy", 5)])[0]
    assert s["profit_factor"] is None


def test_effective_return_sign_convention_holds_across_a_real_replay():
    """A SELL is graded as a win when price FALLS, matching scorecard.py. If
    these ever disagree, live and backtest win rates silently mean different
    things. Asserted over actual replay output, not a restated formula."""
    sigs = []
    for sym in ("NVDA", "AMD", "TSM"):
        sigs.extend(backtest.replay_symbol(sym, held=True, years=5))
    assert sigs, "replay produced no signals to check the convention against"

    for s in sigs:
        for h in backtest.HORIZONS:
            expected = s[f"fwd_{h}"] if s["side"] == "buy" else -s[f"fwd_{h}"]
            assert abs(s[f"eff_{h}"] - expected) < 0.011, s


def test_rules_sorted_best_first():
    sigs = [_sig("bad", "buy", -4), _sig("good", "buy", 9), _sig("mid", "buy", 2)]
    assert [s["rule"] for s in backtest._rule_stats(sigs)] == ["good", "mid", "bad"]


# -------------------------------------------------------------- end to end
def test_run_produces_an_honest_report():
    r = backtest.run(years=5, limit=4)
    assert r["universe"] <= 4
    assert r["grade_horizon_days"] == backtest.GRADE_AT
    # The caveats are not decoration — they must ship with the numbers.
    assert any("survivorship" in c.lower() for c in r["caveats"])
    assert any("slippage" in c.lower() for c in r["caveats"])

    # Must actually replay something. This assertion exists because an earlier
    # version passed vacuously: the 1-year history fetch left zero usable bars
    # after the 200-bar warmup, so every symbol was skipped and every stat was
    # None while the test still went green.
    assert r["symbols_tested"] > 0, f"nothing replayed; skipped={r['skipped']}"
    assert r["signals"] > 0
    assert r["win_rate"] is not None
    assert r["period"]["start"] <= r["period"]["end"]
    assert r["rules"], "signals fired but no per-rule stats were aggregated"


def test_short_history_is_reported_as_skipped_not_silently_dropped(monkeypatch):
    """A symbol without enough bars must show up in `skipped`, so a thin report
    can never be mistaken for a rule that simply never fired."""
    short = _series(list(np.linspace(100, 120, 50)))
    monkeypatch.setattr(
        market_data, "get_deep_history",
        lambda sym, years=5: type("MD", (), {"history": short})(),
    )
    r = backtest.run(years=5, limit=3)
    assert r["symbols_tested"] == 0
    assert len(r["skipped"]) == r["universe"]
