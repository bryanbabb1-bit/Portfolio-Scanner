"""Transition plan tests.

    cd backend && .venv/Scripts/python -m pytest tests/test_transition.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"

import pytest  # noqa: E402

from app.services import advisor, transition as tr  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    monkeypatch.setattr(tr.settings, "ADVISOR_ENABLED", True)
    # No core convictions: these tests cover the sequencing mechanics, and
    # must not depend on the live portfolio.json (whose real core list
    # includes MU, which would block the fixture's own step).
    monkeypatch.setattr(tr, "governance", lambda: {
        "approved": False, "thesis": "", "guardrails": [], "long_term": [],
        "allocation_targets": {}, "core_convictions": [],
    })
    yield


ANALYSIS = {
    "equity": 10_000.0, "cash": 0.0, "target_source": "cleansheet",
    "drift_pct": 40.0, "total_return_pct": -7.3,
    "gap": [{"theme": "AI Infrastructure", "target_pct": 21.0,
             "current_pct": 63.0, "delta": -42.0},
            {"theme": "Healthcare", "target_pct": 7.0, "current_pct": 0.0,
             "delta": 7.0}],
    "funding": [{"symbol": "MU", "theme": "AI Infrastructure", "value": 600.0,
                 "weight_pct": 6.0, "pl_pct": -19.2, "suggested_trim": 400.0,
                 "in_target_book": False, "standing_call": "TRIM",
                 "tax": {"at_loss": True, "term": "short", "held_days": 20,
                         "detail": "Books a short-term loss."}}],
    "acquire": [{"symbol": "LLY", "theme": "Healthcare", "target_pct": 7.0,
                 "target_dollars": 700.0, "price": 1226.5, "stop": 1100.0,
                 "why": "Obesity demand."}],
}

REPLY = {
    "headline": "Trim the weakest chip names into strength, rotate into healthcare.",
    "approach": "Sell what the target book does not want first.",
    "first_move": "Trim $400 of MU at market.",
    "steps": [
        {"n": 1, "trigger": "immediately", "sell": "Sell $400 of MU at market.",
         "buy": "", "sell_symbol": "MU", "sell_level": 900.0,
         "buy_symbol": "", "buy_level": 0,
         "why": "Raises cash from the weakest holding.",
         "realizes": "Books a short-term loss you can offset gains with."},
        {"n": 2, "trigger": "LLY pulls back to $1,180", "sell": "",
         "buy": "Buy $400 of LLY near $1,180.", "buy_symbol": "LLY",
         "buy_level": 1180.0, "sell_symbol": "", "sell_level": 0,
         "why": "Opens the healthcare sleeve.", "realizes": ""},
    ],
    "guardrails": ["Stop if the book falls below $8,500."],
}


def _stub(monkeypatch, reply=REPLY):
    seen = {}

    def fake(prompt, resume=None, research=False, model=None):
        seen["prompt"] = prompt
        return json.dumps(reply), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    return seen


# ------------------------------------------------------------------ tax facts
def test_loss_is_flagged_as_harvestable_with_the_wash_sale_rule():
    t = tr._tax_note(-19.2, "2026-07-08")
    assert t["at_loss"] is True
    assert t["term"] == "short"
    assert "offset" in t["detail"]
    assert "30 days" in t["detail"]


def test_short_term_gain_warns_about_the_holding_period():
    t = tr._tax_note(+12.0, "2026-07-08")
    assert t["at_loss"] is False
    assert t["term"] == "short"
    assert "ordinary income" in t["detail"]


def test_missing_purchase_date_reports_unknown_rather_than_guessing():
    """Holdings carry no date. Assuming one would misstate a real tax
    consequence, so the term must degrade to unknown."""
    t = tr._tax_note(-5.0, None)
    assert t["term"] == "unknown"
    assert t["held_days"] is None


def test_long_held_position_is_long_term():
    t = tr._tax_note(+30.0, "2020-01-01")
    assert t["term"] == "long"
    assert "lower rate" in t["detail"]


# -------------------------------------------------------------- the prompt
def test_prompt_states_every_buy_must_be_funded(monkeypatch):
    """With zero cash this is the constraint that makes the plan real."""
    p = tr._prompt(ANALYSIS)
    assert "funded by a sell" in p.lower() or "FUNDED BY A SALE" in p
    assert "Never propose spending money that does not exist." in p


def test_prompt_carries_the_real_numbers_not_placeholders():
    p = tr._prompt(ANALYSIS)
    assert "MU" in p and "-19.2%" in p
    assert "LLY" in p and "1226.5" in p
    assert "42.0" in p or "-42.0" in p


def test_prompt_permits_taking_a_loss():
    p = tr._prompt(ANALYSIS)
    assert "loss" in p.lower()
    assert "wash-sale" in p.lower()


# ------------------------------------------------------------------ generate
def test_generate_produces_ordered_steps(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    plan = tr.generate()
    assert plan["engine"] == "claude"
    assert [s["n"] for s in plan["steps"]] == [1, 2]
    assert plan["steps"][0]["sell_symbol"] == "MU"
    assert plan["steps"][1]["buy_symbol"] == "LLY"
    assert all(s["done"] is False for s in plan["steps"])


def test_steps_are_sorted_even_if_the_model_returns_them_jumbled(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    jumbled = {**REPLY, "steps": list(reversed(REPLY["steps"]))}
    _stub(monkeypatch, jumbled)
    assert [s["n"] for s in tr.generate()["steps"]] == [1, 2]


def test_no_target_blocks_rather_than_inventing_one(monkeypatch):
    monkeypatch.setattr(tr, "analyse",
                        lambda: {**ANALYSIS, "target_source": "none"})
    called = []
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: called.append(1) or (None, None))
    plan = tr.generate()
    assert plan["engine"] == "blocked"
    assert not called, "must not spend a model call with nothing to aim at"
    assert "Clean Sheet" in plan["error"]


def test_unreachable_desk_degrades_cleanly(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    monkeypatch.setattr(advisor, "_run_claude", lambda *a, **k: (None, None))
    plan = tr.generate()
    assert plan["engine"] == "unavailable"
    assert plan["steps"] == []


# ------------------------------------------------------------------ activate
def test_activate_watchlists_targets_and_creates_watchpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    tr.generate()

    saved = {}
    monkeypatch.setattr(tr.pf_service, "load_portfolio",
                        lambda: {"holdings": [{"symbol": "MU"}], "watchlist": []})
    monkeypatch.setattr(tr.pf_service, "save_portfolio",
                        lambda cfg: saved.update(cfg) or cfg)
    made = []
    monkeypatch.setattr(tr.watchpoints, "add",
                        lambda *a, **k: made.append((a, k)) or {"id": "x"})

    out = tr.activate()
    assert out["watched"] == ["LLY"]           # target added to the watchlist
    assert [w["symbol"] for w in saved["watchlist"]] == ["LLY"]
    assert out["watchpoints"] == 2             # one buy level, one sell level
    kinds = {a[1] for a, _ in made}
    assert kinds == {"price_below", "price_above"}


def test_activate_does_not_duplicate_an_already_watched_name(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    tr.generate()
    monkeypatch.setattr(tr.pf_service, "load_portfolio",
                        lambda: {"holdings": [], "watchlist": [{"symbol": "LLY"}]})
    saves = []
    monkeypatch.setattr(tr.pf_service, "save_portfolio", lambda cfg: saves.append(cfg))
    monkeypatch.setattr(tr.watchpoints, "add", lambda *a, **k: {"id": "x"})
    assert tr.activate()["watched"] == []
    assert not saves, "nothing new to add, so the config must not be rewritten"


def test_activate_with_no_plan_is_refused(monkeypatch):
    assert "No plan" in tr.activate()["error"]


# ------------------------------------------------------------------ progress
def test_marking_a_step_done_persists(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    tr.generate()
    assert tr.set_step_done(1)["done"] is True
    assert tr._load()["steps"][0]["done"] is True
    assert tr.set_step_done(1, False)["done"] is False
    assert tr.set_step_done(99) is None


def test_facts_block_speaks_for_a_draft_plan_too(monkeypatch):
    """Gating this on ACTIVATION was a bug: a generated-but-not-activated plan
    was invisible to the advisor, so the brief and the plan issued conflicting
    orders on the same book. Activation controls monitoring, not whether the
    plan is the client's standing intent."""
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    tr.generate()

    block = tr.facts_block()
    assert "STANDING TRANSITION PLAN" in block
    assert "DRAFT" in block
    assert "OUTSTANDING step 1" in block

    plan = tr._load()
    plan["activated"] = True
    tr._save(plan)
    assert "[ACTIVE]" in tr.facts_block()


def test_facts_block_separates_outstanding_from_completed(monkeypatch):
    monkeypatch.setattr(tr, "analyse", lambda: ANALYSIS)
    _stub(monkeypatch)
    tr.generate()
    tr.set_step_done(1)

    block = tr.facts_block()
    assert "ALREADY DONE" in block          # step 1, executed
    assert "OUTSTANDING step 2" in block    # step 2, still to do
    assert "OUTSTANDING step 1" not in block
