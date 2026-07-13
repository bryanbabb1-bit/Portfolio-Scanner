"""Tests for the Stay-the-Course read (services/staycourse.py).

    cd backend && .venv/Scripts/python -m pytest tests/test_staycourse.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import insights, staycourse  # noqa: E402
from app.services import portfolio as pf_service  # noqa: E402


def _read():
    summary, reports = pf_service.portfolio_summary()
    risk = insights.compute_risk(reports)
    alerts = insights.build_alerts(reports)
    return staycourse.read(summary, reports, risk, alerts), reports


def test_read_shape():
    read, reports = _read()
    assert read["posture"] in ("hold", "act")
    assert read["headline"] and isinstance(read["headline"], str)
    assert read["reasons"] and all(isinstance(r, str) for r in read["reasons"])
    assert read["closer"]
    m = read["metrics"]
    # holdings count matches the held book, and above-trend never exceeds it
    assert m["holdings"] == len([r for r in reports if (r.market_value or 0) > 0 and r.shares])
    assert 0 <= m["above_trend"] <= m["holdings"]


def test_posture_matches_signals():
    read, _ = _read()
    m = read["metrics"]
    # posture is 'act' iff there is something to act on (a ready move or a
    # critical alert); otherwise it must be a reassuring 'hold'.
    should_act = m["ready_count"] > 0 or m["critical_count"] > 0
    assert read["posture"] == ("act" if should_act else "hold")


def test_reasons_are_plain_no_jargon():
    # the DETERMINISTIC reasons (the Claude-off fallback) must never leak the
    # jargon Bryan doesn't want to read.
    read, _ = _read()
    blob = " ".join(read["reasons"]).lower()
    for term in ("rsi", "macd", "sma", "bollinger", "200-day", "death cross"):
        assert term not in blob


def test_act_reasons_name_the_real_alert():
    # when a critical alert drives the 'act' posture, the flagged ticker must be
    # cited by name — never guessed (the bug the first live render surfaced).
    read, _ = _read()
    m = read["metrics"]
    if m["critical_count"] > 0:
        assert m["flagged"], "critical alerts must be listed in metrics.flagged"
        named = m["flagged"][0].split(" ")[0]
        assert any(named in r for r in read["reasons"])
