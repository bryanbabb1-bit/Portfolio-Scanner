"""Robustness matrix tests.

    cd backend && .venv/Scripts/python -m pytest tests/test_robustness.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from app.services import robustness  # noqa: E402


def _sig(rule, date, eff5=1.0, eff20=1.0, eff60=1.0, side="buy"):
    return {"symbol": "AAA", "date": date, "rule": rule, "side": side,
            "price": 100.0, "score": 50.0, "bar": 1,
            "fwd_5": eff5, "fwd_20": eff20, "fwd_60": eff60,
            "eff_5": eff5, "eff_20": eff20, "eff_60": eff60, "mae_pct": -3.0}


@pytest.fixture
def regimes(monkeypatch):
    """Three fixed dates, one per regime — no market data needed."""
    monkeypatch.setattr(robustness, "regime_map", lambda years=5: {
        "2024-01-01": "rising",
        "2024-02-01": "flat",
        "2024-03-01": "falling",
    })


def _many(rule, date, n, eff20, **kw):
    return [_sig(rule, date, eff20=eff20, **kw) for _ in range(n)]


# ------------------------------------------------------------ regime split
def test_regime_uses_trailing_not_forward_return():
    """The split must be knowable AT signal time, or 'works in downtrends'
    becomes a hindsight claim you could never have acted on."""
    idx = pd.date_range("2024-01-01", periods=60, freq="B")
    # First half falls hard, second half rips.
    closes = list(range(100, 70, -1)) + list(range(70, 100))
    hist = pd.DataFrame({"Close": [float(c) for c in closes]}, index=idx)

    class MD:
        history = hist

    import app.services.market_data as md_mod
    orig = md_mod.get_deep_history
    md_mod.get_deep_history = lambda sym, years=5: MD()
    try:
        m = robustness.regime_map()
    finally:
        md_mod.get_deep_history = orig

    # A date in the middle of the decline is 'falling'; late in the rally,
    # 'rising'. If forward returns were used these would be inverted.
    assert m[idx[25].strftime("%Y-%m-%d")] == "falling"
    assert m[idx[-1].strftime("%Y-%m-%d")] == "rising"


# ------------------------------------------------------------- the verdicts
def test_positive_everywhere_is_robust(regimes):
    sigs = (_many("r", "2024-01-01", 20, 3.0)
            + _many("r", "2024-02-01", 20, 3.0)
            + _many("r", "2024-03-01", 20, 3.0))
    row = robustness.matrix(sigs)["rules"][0]
    assert row["verdict"] == "ROBUST"


def test_negative_everywhere_is_broken(regimes):
    sigs = (_many("r", "2024-01-01", 20, -4.0, eff5=-2.0, eff60=-8.0)
            + _many("r", "2024-02-01", 20, -4.0, eff5=-2.0, eff60=-8.0)
            + _many("r", "2024-03-01", 20, -4.0, eff5=-2.0, eff60=-8.0))
    row = robustness.matrix(sigs)["rules"][0]
    assert row["verdict"] == "BROKEN"
    assert "the rule, not the test" in row["reason"]


def test_sign_flip_across_regimes_is_fragile(regimes):
    """The case the whole matrix exists for: good in rising, bad in falling.
    A single headline average would have hidden this."""
    sigs = (_many("r", "2024-01-01", 20, 6.0, eff5=6.0, eff60=6.0)
            + _many("r", "2024-02-01", 20, 4.0, eff5=4.0, eff60=4.0)
            + _many("r", "2024-03-01", 20, -9.0, eff5=-9.0, eff60=-9.0))
    row = robustness.matrix(sigs)["rules"][0]
    assert row["verdict"] == "FRAGILE"
    assert "falling" in row["reason"]


def test_thin_coverage_is_unproven_not_a_verdict(regimes):
    """Three signals is not evidence, however extreme they look."""
    sigs = _many("r", "2024-01-01", 3, -20.0)
    row = robustness.matrix(sigs)["rules"][0]
    assert row["verdict"] == "UNPROVEN"
    assert all(c["thin"] for c in row["cells"].values() if c["n"])


def test_thin_cells_are_flagged_not_hidden(regimes):
    sigs = _many("r", "2024-01-01", 40, 2.0) + _many("r", "2024-03-01", 2, 9.0)
    cells = robustness.matrix(sigs)["rules"][0]["cells"]
    assert cells["rising"]["thin"] is False
    assert cells["falling"]["thin"] is True
    assert cells["falling"]["n"] == 2       # reported, just not trusted


def test_worst_rules_sort_first(regimes):
    sigs = (_many("good", "2024-01-01", 20, 3.0) + _many("good", "2024-02-01", 20, 3.0)
            + _many("good", "2024-03-01", 20, 3.0)
            + _many("bad", "2024-01-01", 20, -3.0) + _many("bad", "2024-02-01", 20, -3.0)
            + _many("bad", "2024-03-01", 20, -3.0))
    assert [r["rule"] for r in robustness.matrix(sigs)["rules"]] == ["bad", "good"]


# ------------------------------------------------- crash-rule retirement check
def test_retiring_a_rule_untested_in_falling_markets_warns(regimes):
    """The smoke-alarm case: retired on rising/flat evidence, never measured
    where it was supposed to matter."""
    sigs = _many("crash-rule", "2024-01-01", 40, -5.0) + _many("crash-rule", "2024-02-01", 40, -5.0)
    m = robustness.matrix(sigs)
    warns = robustness.crash_rule_warnings(m, {"crash-rule"})
    assert warns and "NEVER fired in a falling market" in warns[0]


def test_retiring_a_rule_that_works_in_falls_warns_loudly(regimes):
    sigs = (_many("crash-rule", "2024-01-01", 40, -6.0)
            + _many("crash-rule", "2024-03-01", 30, +8.0))
    warns = robustness.crash_rule_warnings(robustness.matrix(sigs), {"crash-rule"})
    assert warns and "reconsider" in warns[0]


def test_a_rule_bad_in_falls_too_produces_no_warning(regimes):
    """sharp-breakdown's real shape: worst exactly where it should have
    helped. Retirement is confirmed, so say nothing."""
    sigs = (_many("crash-rule", "2024-01-01", 40, -6.0)
            + _many("crash-rule", "2024-02-01", 40, -7.0)
            + _many("crash-rule", "2024-03-01", 40, -17.0))
    assert robustness.crash_rule_warnings(robustness.matrix(sigs), {"crash-rule"}) == []


def test_non_retired_rules_are_never_warned_about(regimes):
    sigs = _many("live-rule", "2024-01-01", 40, -6.0)
    assert robustness.crash_rule_warnings(robustness.matrix(sigs), set()) == []


def test_missing_benchmark_degrades_cleanly(monkeypatch):
    monkeypatch.setattr(robustness, "regime_map", lambda years=5: {})
    m = robustness.matrix([_sig("r", "2024-01-01")])
    assert m["rules"] == []
    assert "unavailable" in m["note"].lower()
