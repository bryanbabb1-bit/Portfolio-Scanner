"""Standing preferences are constraints, not requests.

Bryan told the advisor four times not to recommend SBUX, VXUS or DE. It agreed
every time and then led the next brief with "Buy $250 VXUS" and "Buy $200
SBUX", calling VXUS "still my number one, unchanged". The chat log had every
word; the brief never read it.

So these tests cover the ENFORCEMENT, not the prompt. A prompt is a request —
we have four recorded instances of it being ignored.

    cd backend && .venv/Scripts/python -m pytest tests/test_preferences.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import preferences as p  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "_FILE", tmp_path / "preferences.json")
    yield


# --------------------------------------------------------------------- store
def test_a_block_survives_and_is_listed():
    p.block("SBUX", reason="not interested in retail")
    assert "SBUX" in p.blocked_symbols()


def test_blocking_twice_does_not_duplicate():
    p.block("VXUS")
    p.block("VXUS", reason="said again")
    assert len(p.get()["blocked"]) == 1


def test_a_block_can_be_lifted():
    p.block("DE")
    p.unblock("DE")
    assert "DE" not in p.blocked_symbols()


def test_lowercase_input_is_normalised():
    p.block("sbux")
    assert "SBUX" in p.blocked_symbols()


# ------------------------------------------------------------------- prompts
def test_the_constraint_names_every_blocked_ticker():
    for s in ("SBUX", "VXUS", "DE"):
        p.block(s)
    text = p.block_text()
    for s in ("SBUX", "VXUS", "DE"):
        assert s in text
    assert "NEVER RECOMMEND" in text


def test_wanted_themes_reach_the_prompt():
    p.want("energy")
    p.want("high growth")
    text = p.block_text()
    assert "energy" in text and "high growth" in text


def test_no_preferences_means_no_wasted_prompt_space():
    assert p.block_text() == ""


# ------------------------------------------------------------------ enforcing
def test_a_buy_order_for_a_blocked_name_is_removed():
    """The exact line from the 2026-08-26 09:42 brief."""
    p.block("VXUS")
    kept, removed = p.filter_actions([
        "Hold NVDA and CRWD through tonight's earnings - no trades.",
        "Buy $250 VXUS at $88.04.",
        "Hold everything else - do nothing.",
    ])
    assert len(kept) == 2
    assert removed == ["VXUS"]
    assert not any("VXUS" in k for k in kept)


def test_selling_a_blocked_name_is_still_allowed():
    """He owns some of these. Refusing to discuss an EXIT would be a different
    kind of unhelpful."""
    p.block("SBUX")
    kept, removed = p.filter_actions(["Sell all $200 SBUX at market."])
    assert kept and not removed


def test_holding_a_blocked_name_is_still_allowed():
    p.block("SBUX")
    kept, removed = p.filter_actions(["Hold SBUX - no action."])
    assert kept and not removed


def test_a_championed_idea_for_a_blocked_name_is_dropped():
    """'HIGH CONVICTION VXUS ... still my number one, unchanged' — verbatim."""
    p.block("VXUS")
    kept, removed = p.filter_scout([
        "HIGH CONVICTION VXUS at $88.04 - still my number one, unchanged.",
        "HIGH CONVICTION AVUV at market - 600 cheap smaller businesses.",
    ])
    assert len(kept) == 1 and "AVUV" in kept[0]
    assert removed == ["VXUS"]


def test_structured_plan_steps_are_filtered_too():
    p.block("SBUX")
    kept, removed = p.filter_actions([
        {"n": 1, "when": "immediately", "do": "Buy $200 SBUX at market",
         "why": "turnaround"},
        {"n": 2, "when": "immediately", "do": "Buy $250 GEV at market",
         "why": "energy"},
    ])
    assert len(kept) == 1 and kept[0]["n"] == 2
    assert removed == ["SBUX"]


def test_english_words_are_not_mistaken_for_tickers():
    """'Buy $250 GEV AT market' must not trip on AT, IT, or A."""
    p.block("IT")
    kept, removed = p.filter_actions(["Buy $250 GEV at market when you can."])
    assert kept and not removed


def test_candidates_are_filtered_before_the_model_sees_them():
    p.block("SBUX")
    out = p.filter_candidates([{"symbol": "SBUX"}, {"symbol": "GEV"},
                               {"symbol": "sbux"}])
    assert [c["symbol"] for c in out] == ["GEV"]


def test_nothing_blocked_changes_nothing():
    items = ["Buy $250 VXUS at $88.04.", "Hold NVDA."]
    kept, removed = p.filter_actions(items)
    assert kept == items and removed == []
