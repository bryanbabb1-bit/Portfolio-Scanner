"""Tests for the sequenced game-plan reconciler (services/plan.py).

    cd backend && .venv/Scripts/python -m pytest tests/test_plan.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import plan  # noqa: E402


def test_side_detection():
    assert plan._side("Buy $150 NVDA near $191") == "buy"
    assert plan._side("Add $150 AVGO on a dip") == "buy"
    assert plan._side("Trim $400 IREN near $41") == "sell"
    assert plan._side("Sell all IREN") == "sell"
    assert plan._side("Hold everything else") == "hold"
    assert plan._side("Skip TC — already up huge") == "hold"


def test_parse_amount_vs_level():
    # the amount is the position size after the verb; the level is the entry
    t = "Buy $150 NVDA near $191 using the trim cash."
    assert plan._parse_amount(t) == 150.0
    assert plan._parse_level(t) == 191.0
    t2 = "Trim $400 IREN near $41; move proceeds to cash."
    assert plan._parse_amount(t2) == 400.0
    assert plan._parse_level(t2) == 41.0
    # "below here" has no number → no level
    assert plan._parse_level("Add $150 AVGO on any further dip below here.") is None


def test_find_symbol():
    known = {"NVDA", "AVGO", "IREN", "MU"}
    assert plan._find_symbol("Buy $150 NVDA near $191", known) == "NVDA"
    assert plan._find_symbol("Trim $400 IREN near $41", known) == "IREN"
    assert plan._find_symbol("Take some cash off", known) is None


def test_buy_gate_waits_for_dip():
    # want to buy at $191 but price is $195 → not met, must fall
    g = plan._price_gate("buy", "Buy NVDA near $191", 191.0, 195.0)
    assert g["direction"] == "fall" and g["met"] is False
    # price fell to the level → ready
    g2 = plan._price_gate("buy", "Buy NVDA near $191", 191.0, 190.5)
    assert g2["met"] is True


def test_trim_gate_waits_for_bounce():
    # trim into strength at $44, price $42 → needs to rise, not met
    g = plan._price_gate("sell", "Trim IREN if it bounces to $44", 44.0, 42.0)
    assert g["direction"] == "rise" and g["met"] is False
    g2 = plan._price_gate("sell", "Trim IREN if it bounces to $44", 44.0, 44.5)
    assert g2["met"] is True


def test_stop_gate_is_a_fall():
    # a stop/sell-on-weakness is the opposite direction
    g = plan._price_gate("sell", "Sell IREN if it drops below $38", 38.0, 40.0)
    assert g["direction"] == "fall" and g["met"] is False


def test_floor_from_strategy_or_default():
    assert plan._floor({"allocation_targets": {"Cash & Income": 16}}, 10_000) == (1600, 16.0)
    # no cash target → 15% fallback
    assert plan._floor({"allocation_targets": {"AI": 30}}, 10_000) == (1500, 15.0)
    assert plan._floor(None, 10_000) == (1500, 15.0)


def test_stop_is_not_a_funder():
    # a protective stop (sell on a drop / "stop loss") is a guard, never a
    # cash-raising trim, so it must not fund other buys
    stop = {"side": "sell", "text": "Sell NVDA if it drops to $185 (stop loss)",
            "symbol": "NVDA", "gate": {"direction": "fall", "met": False}}
    trim = {"side": "sell", "text": "Trim $400 IREN; move proceeds to cash",
            "symbol": "IREN", "gate": {"direction": "rise", "met": False}}
    assert plan._is_stop(stop) is True
    assert plan._is_stop(trim) is False


def test_build_plan_shape():
    p = plan.build_plan()
    for key in ("dry_powder", "floor", "below_floor", "queued_buys",
                "ready", "waiting", "funders", "count"):
        assert key in p
    assert isinstance(p["ready"], list) and isinstance(p["waiting"], list)
    # every move is bucketed with a status
    for m in p["ready"] + p["waiting"]:
        assert m["status"] in ("ready", "waiting")
