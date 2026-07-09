"""Tests for realized-P/L helpers (pure — no journal-file writes).

    cd backend && .venv/Scripts/python -m pytest tests/test_realized.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import journal  # noqa: E402


def test_realized_gain_and_loss():
    # sold 10 sh at $30, cost $25 → +$50
    assert journal._realized(10, 30.0, 25.0) == 50.0
    # the IREN case: sold at a loss
    assert journal._realized(28.5789, 39.0, 56.5) == round(28.5789 * (39.0 - 56.5), 2)
    assert journal._realized(28.5789, 39.0, 56.5) < 0


def test_realized_needs_all_inputs():
    assert journal._realized(None, 30.0, 25.0) is None
    assert journal._realized(10, None, 25.0) is None
    assert journal._realized(10, 30.0, None) is None


def test_norm_snapshot_reads_both_formats():
    # legacy {sym: shares}
    legacy = journal._norm_snap({"NVDA": 5.0, "IREN": 28.0})
    assert legacy["NVDA"] == {"shares": 5.0, "cost": None}
    # current {sym: {shares, cost}}
    cur = journal._norm_snap({"NVDA": {"shares": 5.0, "cost": 205.38}})
    assert cur["NVDA"]["shares"] == 5.0 and cur["NVDA"]["cost"] == 205.38
    assert journal._norm_snap([]) == {}
