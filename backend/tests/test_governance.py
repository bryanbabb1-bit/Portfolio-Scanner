"""Governance: the approved strategy outranks everything downstream.

The failure this exists to prevent: the transition plan staged out of AVGO — a
designated core conviction the approved strategy says to hold for years and
never sell on price — while the brief and the stance ledger both said HOLD.
Root cause was _target() preferring the Clean Sheet, which is built BLIND to
the strategy on purpose, so a context-free diagnostic became the destination.

    cd backend && .venv/Scripts/python -m pytest tests/test_governance.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"

import pytest  # noqa: E402

from app.services import advisor, transition as tr  # noqa: E402

STRATEGY = {
    "approved": True,
    "thesis": "Own the AI buildout.",
    "allocation_targets": {"AI Infrastructure": 28, "AI": 20, "Healthcare": 14},
    "guardrails": ["Core names are sold only on broken business news."],
    "long_term": ["Core to hold for years: NVDA, AVGO — never sell on price."],
}
CLEANSHEET = {
    "allocation": [{"theme": "AI Infrastructure", "pct": 21, "why": ""},
                   {"theme": "Compute Power", "pct": 20, "why": ""}],
    "picks": [{"symbol": "VRT", "theme": "Compute Power", "pct": 20, "why": ""},
              {"symbol": "LLY", "theme": "Healthcare", "pct": 14, "why": ""}],
}
CORE = ["NVDA", "AVGO", "GOOGL"]


@pytest.fixture(autouse=True)
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_FILE", tmp_path / "transition.json")
    monkeypatch.setattr(tr.stance_service, "_FILE", tmp_path / "stances.json")
    monkeypatch.setattr(tr.settings, "ADVISOR_ENABLED", True)
    monkeypatch.setattr(tr.strategy_service, "load", lambda: dict(STRATEGY))
    monkeypatch.setattr(tr.cleansheet, "last_result", lambda *a, **k: dict(CLEANSHEET))
    monkeypatch.setattr(tr.pf_service, "load_portfolio",
                        lambda: {"core_convictions": list(CORE),
                                 "holdings": [], "watchlist": []})
    yield


# --------------------------------------------------------- order of authority
def test_approved_strategy_is_the_target_not_the_clean_sheet():
    """THE bug. The Clean Sheet is built blind to the strategy, so letting it
    set the destination inverts the hierarchy."""
    alloc, picks, source = tr._target()
    assert source == "strategy"
    assert alloc["AI Infrastructure"] == 28      # strategy's number, not 21
    assert "Compute Power" not in alloc          # a sleeve the strategy omits


def test_clean_sheet_names_are_kept_only_for_sleeves_the_strategy_wants():
    """It can fill in NAMES for a sleeve the strategy asked for without
    naming one; it can never smuggle in a sleeve of its own."""
    _alloc, picks, _ = tr._target()
    syms = {p["symbol"] for p in picks}
    assert "LLY" in syms                          # Healthcare: strategy wants it
    assert "VRT" not in syms                      # Compute Power: it does not


def test_clean_sheet_only_governs_with_no_approved_strategy(monkeypatch):
    monkeypatch.setattr(tr.strategy_service, "load",
                        lambda: {**STRATEGY, "approved": False})
    _alloc, _picks, source = tr._target()
    assert source.startswith("cleansheet")
    assert "no approved strategy" in source       # labelled, not silent


# ------------------------------------------------- core convictions in CODE
def _reply_selling(symbol):
    return {
        "headline": "h", "approach": "a", "first_move": "f", "guardrails": [],
        "steps": [{"n": 1, "trigger": "AVGO bounces", "buy": "",
                   "sell": f"Sell $675 of {symbol}, about half the position.",
                   "sell_symbol": symbol, "sell_level": 390.0,
                   "buy_symbol": "", "buy_level": 0,
                   "why": "raise cash", "realizes": "short-term loss"}],
    }


def test_a_step_selling_a_core_conviction_is_blocked(monkeypatch):
    """Enforced in code, not asked of the model — this one protects real money."""
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("AVGO")), "s"))
    step = tr.generate()["steps"][0]
    assert step["blocked"] is True
    assert "core conviction" in step["blocked_reason"].lower()
    assert "AVGO" in step["blocked_reason"]


def test_a_blocked_step_cannot_be_marked_done(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("AVGO")), "s"))
    tr.generate()
    assert tr.set_step_done(1)["done"] is False
    assert tr.completed_moves() == []


def test_a_blocked_step_never_arms_a_trigger(monkeypatch):
    """The dangerous failure: a blocked step quietly creating a live sell
    watchpoint on a name the strategy protects."""
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("AVGO")), "s"))
    tr.generate()
    made = []
    monkeypatch.setattr(tr.watchpoints, "add",
                        lambda *a, **k: made.append(a) or {"id": "x"})
    monkeypatch.setattr(tr.pf_service, "save_portfolio", lambda cfg: cfg)
    tr.activate()
    assert made == []


def test_a_non_core_name_is_not_blocked(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("MU")), "s"))
    step = tr.generate()["steps"][0]
    assert step["blocked"] is False
    assert tr.set_step_done(1)["done"] is True


def test_the_prompt_states_the_constitution(monkeypatch):
    seen = {}

    def fake(prompt, resume=None, research=False, model=None):
        seen["p"] = prompt
        return json.dumps(_reply_selling("MU")), "s"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    tr.generate()
    p = seen["p"]
    assert "CORE CONVICTIONS" in p and "AVGO" in p
    assert "HARD GUARDRAILS" in p
    assert "never sell on price" in p.lower() or "never sell a core" in p.lower()


# ------------------------------------------------------------- coherence
def test_coherence_flags_a_core_conviction_sale_as_critical(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("AVGO")), "s"))
    tr.generate()
    c = tr.coherence()
    assert c["clean"] is False
    top = c["conflicts"][0]
    assert top["severity"] == "critical"
    assert top["symbol"] == "AVGO"


def test_coherence_flags_a_sale_against_a_standing_hold(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("MU")), "s"))
    tr.generate()
    tr.stance_service.set_stance("MU", "HOLD", headline="Hold MU.")
    conflicts = tr.coherence()["conflicts"]
    assert any(c["symbol"] == "MU" and c["severity"] == "warning" for c in conflicts)


def test_coherence_reports_strategy_vs_cleansheet_drift(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("MU")), "s"))
    tr.generate()
    info = [c for c in tr.coherence()["conflicts"] if c["severity"] == "info"]
    assert any("Compute Power" in c["symbol"] or "Healthcare" in c["symbol"]
               for c in info)


def test_a_clean_plan_reports_clean(monkeypatch):
    monkeypatch.setattr(tr.cleansheet, "last_result", lambda *a, **k: None)
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("MU")), "s"))
    tr.generate()
    assert tr.coherence()["clean"] is True


def test_facts_block_marks_blocked_steps_as_do_not_act(monkeypatch):
    """The advisor must not repeat a blocked instruction back at the client."""
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (json.dumps(_reply_selling("AVGO")), "s"))
    tr.generate()
    block = tr.facts_block()
    assert "BLOCKED" in block
    assert "do NOT act" in block
