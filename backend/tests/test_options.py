"""Tests for the options engine's pure helpers (no network).

    cd backend && .venv/Scripts/python -m pytest tests/test_options.py -q
"""
import math
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import options  # noqa: E402


def test_nan_safe_float():
    assert options._f(float("nan")) == 0.0
    assert options._f(float("nan"), 5) == 5.0
    assert options._f(None) == 0.0
    assert options._f("3.5") == 3.5
    assert options._f(12) == 12.0


def test_bs_delta_bounds():
    # a call delta is between 0 and 1; ATM ~0.5-0.6
    d = options._bs_delta(spot=100, strike=100, t_years=0.33, iv=0.45, call=True)
    assert d is not None and 0.4 < d < 0.75
    # deep ITM call -> delta near 1
    assert options._bs_delta(100, 50, 0.33, 0.45, True) > 0.9
    # a put delta is negative
    p = options._bs_delta(100, 100, 0.33, 0.45, call=False)
    assert p is not None and -0.75 < p < -0.25
    # degenerate inputs -> None
    assert options._bs_delta(100, 100, 0, 0.45, True) is None
    assert options._bs_delta(100, 100, 0.33, 0, True) is None


def test_suggest_none_in_mock():
    # no live chain in mock mode — must degrade gracefully, never raise
    assert options.suggest("NVDA", "call") is None
