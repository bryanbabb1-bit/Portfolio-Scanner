"""Risk desk tests — deterministic mock data, no network, no claude.

    cd backend && .venv/Scripts/python -m pytest tests/test_risk.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.config import settings  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AnalystView, Indicators, Quote, StockReport,
)
from app.services import risk  # noqa: E402


def _report(price=100.0, atr=None, sma200=None, **overrides) -> StockReport:
    base = dict(
        symbol="TEST",
        quote=Quote(symbol="TEST", price=price, change=0.0, change_pct=0.0,
                    volume=5_000_000, source="mock"),
        indicators=Indicators(rsi=50, atr=atr, sma50=95, sma200=sma200,
                              trend="uptrend", volume_ratio=1.0),
        analyst=AnalystView(),
    )
    base.update(overrides)
    return StockReport(**base)


# ------------------------------------------------------------------- stops
def test_stop_uses_atr_when_no_usable_sma200():
    stop, basis = risk.stop_for(_report(price=100, atr=3))
    assert stop == 94.0                      # 100 - 2 x 3
    assert "ATR" in basis


def test_stop_takes_the_tighter_of_atr_and_200day():
    # 200-day at 97 is closer to price than the 94 ATR stop -> it wins.
    stop, basis = risk.stop_for(_report(price=100, atr=3, sma200=97))
    assert stop == 97.0
    assert basis == "200-day"


def test_sma200_above_price_is_a_target_not_a_stop():
    """A 200-day overhead must never be used as a stop — it would be above
    the entry, which would mean 'exit at a profit if it falls'."""
    stop, basis = risk.stop_for(_report(price=100, atr=3, sma200=120))
    assert stop == 94.0
    assert "ATR" in basis


def test_stop_is_none_without_atr_or_sma200():
    stop, basis = risk.stop_for(_report(price=100))
    assert stop is None and basis is None


# ------------------------------------------------------------------ sizing
def test_size_is_risk_based_not_dollar_based():
    """The whole point: a wider stop must buy a SMALLER position, so the
    dollars at risk stay constant across names.

    Both stops here are wide enough that the max-position cap doesn't bind —
    when it does bind it lowers risk below budget, which is tested separately.
    """
    equity = 10_000.0
    tight = risk.plan_for(_report(price=100, atr=3), equity, cash=equity)   # stop 94
    wide = risk.plan_for(_report(price=100, atr=6), equity, cash=equity)    # stop 88

    assert tight.capped_by is None and wide.capped_by is None
    assert tight.dollars > wide.dollars
    budget = equity * settings.RISK_PER_TRADE_PCT / 100
    assert abs(tight.risk_amount - budget) < 1.0
    assert abs(wide.risk_amount - budget) < 1.0


def test_capping_only_ever_lowers_risk():
    """A cap must never let more risk through than the budget allows."""
    equity = 10_000.0
    budget = equity * settings.RISK_PER_TRADE_PCT / 100
    capped = risk.plan_for(_report(price=100, atr=1), equity, cash=equity)
    assert capped.capped_by == "max position"
    assert capped.risk_amount < budget


def test_size_capped_by_max_position():
    # A very tight stop would otherwise size to many times the book.
    plan = risk.plan_for(_report(price=100, atr=0.05), 10_000.0, cash=10_000.0)
    assert plan.capped_by == "max position"
    assert plan.pct_of_equity <= settings.MAX_POSITION_PCT + 0.01


def test_size_capped_by_dry_powder():
    plan = risk.plan_for(_report(price=100, atr=2), 10_000.0, cash=50.0)
    assert plan.capped_by == "dry powder"
    assert plan.dollars <= 50.0


def test_no_stop_means_no_size_and_says_so():
    plan = risk.plan_for(_report(price=100), 10_000.0, cash=10_000.0)
    assert plan.dollars == 0
    assert "stop" in plan.note.lower()


def test_zero_equity_does_not_divide_by_zero():
    plan = risk.plan_for(_report(price=100, atr=2), 0.0, cash=0.0)
    assert plan.dollars == 0


# --------------------------------------------------------------- the desk
def test_risk_desk_reports_real_shape():
    d = risk.risk_desk()
    assert d.equity > 0
    assert d.status in {"PROTECTED", "ELEVATED", "BREACHED"}
    assert d.daily_loss_limit_pct == settings.DAILY_LOSS_LIMIT_PCT
    assert 0 <= d.exposure_utilization_pct <= 100.01
    # Open risk is the sum of the per-position risks it actually reported.
    summed = sum(p.risk_amount or 0 for p in d.positions)
    assert abs(summed - (d.portfolio_risk_amount or 0)) < 1.0


def test_var_and_correlation_are_gated_on_sample_size(monkeypatch):
    """Below the minimum sample the desk must report the shortfall, not a
    number — a VaR computed on 10 days is worse than no VaR."""
    monkeypatch.setattr(settings, "RISK_MIN_DAYS", 10_000)
    d = risk.risk_desk()
    assert d.var95_pct is None
    assert d.avg_correlation is None
    assert any("value-at-risk" in n.lower() for n in d.notes)


def test_facts_block_is_prompt_safe():
    block = risk.facts_block()
    assert "RISK DESK" in block
    assert "Risk budget per new trade" in block
