"""Agent debate tests — the CLI is stubbed, so no model is ever invoked.

    cd backend && .venv/Scripts/python -m pytest tests/test_debate.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"

import pytest  # noqa: E402

from app.services import advisor, debate  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    """Never touch the real debates.json / stance ledger.

    ADVISOR_ENABLED is set on the settings object, not via os.environ: the
    Settings singleton is built at import time, and sibling test modules set
    that env var to "0" first, so an env tweak here would arrive too late.
    """
    monkeypatch.setattr(debate.settings, "ADVISOR_ENABLED", True)
    monkeypatch.setattr(debate, "_FILE", tmp_path / "debates.json")
    monkeypatch.setattr(debate.stance_service, "_FILE", tmp_path / "stances.json")
    yield


def _stub_cli(monkeypatch, agent_reply: dict, judge_reply: dict):
    """Route the five agent calls and the judge call to canned JSON.

    The judge is the only call made WITHOUT an explicit model (it uses the
    CLI default / best model), which is exactly how we tell them apart."""
    calls = []

    def fake(prompt, resume=None, research=False, model=None):
        calls.append({"model": model, "prompt": prompt})
        payload = agent_reply if model else judge_reply
        return json.dumps(payload), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    return calls


AGENT_OK = {
    "position": "BULLISH",
    "confidence": 72,
    "points": ["Revenue grew 40%.", "Margins expanding.", "Backlog at a record."],
    "strongest": "Backlog at a record.",
}
JUDGE_OK = {
    "verdict": "APPROVE",
    "action": "BUY",
    "score": 71,
    "headline": "The bull case survives the margin objection.",
    "rationale": ["Bull's backlog point outweighs Bear's multiple worry."],
    "dissent": ["A cycle turn would invalidate the backlog read."],
    "entry": "$100", "target": "$130", "stop": "$88",
}


# ------------------------------------------------------------------ parsing
def test_json_survives_markdown_fencing_and_prose():
    raw = 'Sure, here you go:\n```json\n{"verdict": "APPROVE", "score": 80}\n```\nHope that helps!'
    assert debate._json_from(raw) == {"verdict": "APPROVE", "score": 80}


def test_json_from_garbage_is_empty_not_an_exception():
    assert debate._json_from("no json here") == {}
    assert debate._json_from("") == {}


def test_confidence_is_clamped_and_defaulted():
    assert debate._clamp_int(150, 0, 100, 50) == 100
    assert debate._clamp_int(-5, 0, 100, 50) == 0
    assert debate._clamp_int("banana", 0, 100, 50) == 50
    assert debate._clamp_int(None, 0, 100, 50) == 50


# ------------------------------------------------------------ orchestration
def test_convene_runs_five_agents_and_one_judge(monkeypatch):
    calls = _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    result = debate.convene("NVDA", force=True)

    assert len(calls) == 6
    # Five agents on the standard tier, judge on the CLI default (best) model.
    assert sum(1 for c in calls if c["model"]) == 5
    assert sum(1 for c in calls if c["model"] is None) == 1
    assert len(result["agents"]) == 5
    assert {a["key"] for a in result["agents"]} == {
        "bull", "bear", "macro", "risk", "execution"
    }


def test_round_two_agents_see_round_one(monkeypatch):
    """Risk and Execution must be briefed with the opening arguments — that is
    the whole point of a second round."""
    calls = _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    debate.convene("NVDA", force=True)

    agent_prompts = [c["prompt"] for c in calls if c["model"]]
    with_prior = [p for p in agent_prompts if "OPENING ARGUMENTS FROM ROUND 1" in p]
    assert len(with_prior) == 2
    # And the round-1 agents must NOT have seen it (nothing existed yet).
    assert len(agent_prompts) - len(with_prior) == 3


def test_verdict_becomes_the_standing_call(monkeypatch):
    """One voice: the ruling writes back to the stance ledger so the dashboard
    can't contradict the desk."""
    _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    debate.convene("NVDA", force=True)

    s = debate.stance_service.get("NVDA")
    assert s and s["action"] == "BUY"
    assert s["source"] == "debate"


def test_sizing_comes_from_the_risk_desk_not_the_model(monkeypatch):
    """The judge rules on WHETHER; HOW MUCH stays deterministic."""
    _stub_cli(monkeypatch, AGENT_OK, {**JUDGE_OK, "dollars": 999_999})
    result = debate.convene("NVDA", force=True)
    assert "dollars" in result["sizing"]
    assert result["sizing"]["dollars"] != 999_999


def test_tally_counts_only_agents_that_reported(monkeypatch):
    """Agents run concurrently, so pick the failures by agent identity rather
    than by a call counter — a shared counter across threads is racy."""
    failing = {"Bull Agent", "Macro Agent"}

    def fake(prompt, resume=None, research=False, model=None):
        if model is None:
            return json.dumps(JUDGE_OK), "sid"
        if any(prompt.startswith(a["brief"][:40]) for a in debate.AGENTS
               if a["name"] in failing):
            return None, None
        return json.dumps(AGENT_OK), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    result = debate.convene("NVDA", force=True)
    assert result["agents_reporting"] == 3
    assert result["tally"]["bullish"] == 3
    # The failed agents are still listed, just with nothing to say.
    silent = [a for a in result["agents"] if not a["ok"]]
    assert {a["name"] for a in silent} == failing


def test_judge_failure_keeps_the_arguments_and_says_so(monkeypatch):
    def fake(prompt, resume=None, research=False, model=None):
        if model is None:
            return None, None          # judge unreachable
        return json.dumps(AGENT_OK), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    result = debate.convene("NVDA", force=True)

    assert result["engine"] == "unavailable"
    assert result["verdict"] == "REJECT"      # never approve without a ruling
    assert len(result["agents"]) == 5         # arguments still shown
    assert "judge" in result["error"].lower()
    # A failed ruling must NOT overwrite the standing call.
    assert debate.stance_service.get("NVDA") is None


def test_bad_verdict_word_fails_closed(monkeypatch):
    _stub_cli(monkeypatch, AGENT_OK, {**JUDGE_OK, "verdict": "MAYBE", "action": "YOLO"})
    result = debate.convene("NVDA", force=True)
    assert result["verdict"] == "REJECT"      # unrecognized -> do not approve
    # An unusable action follows the verdict rather than defaulting to WATCH:
    # WATCH is the one call the scorecard treats as ungradeable, so defaulting
    # there turned every parse failure into a ruling nobody could ever score.
    assert result["action"] == "AVOID"
    assert result["action_inferred"] is True


def test_a_ruled_action_is_not_marked_inferred(monkeypatch):
    _stub_cli(monkeypatch, AGENT_OK, {**JUDGE_OK, "verdict": "REJECT", "action": "WATCH"})
    result = debate.convene("NVDA", force=True)
    assert result["action"] == "WATCH"
    assert result["action_inferred"] is False


# ----------------------------------------------------------------- caching
def test_cache_short_circuits_the_six_calls(monkeypatch):
    calls = _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    debate.convene("NVDA", force=True)
    assert len(calls) == 6

    debate.convene("NVDA")                 # cached — must not re-run
    assert len(calls) == 6

    debate.convene("NVDA", force=True)     # explicit refresh — runs again
    assert len(calls) == 12


def test_stale_cache_is_ignored(monkeypatch):
    _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    debate.convene("NVDA", force=True)
    assert debate.get_cached("NVDA") is not None
    assert debate.get_cached("NVDA", max_age=-1) is None


def test_history_omits_transcripts_and_sorts_newest_first(monkeypatch):
    _stub_cli(monkeypatch, AGENT_OK, JUDGE_OK)
    debate.convene("NVDA", force=True)
    debate.convene("AMD", force=True)

    hist = debate.history()
    assert [h["symbol"] for h in hist] == ["AMD", "NVDA"]
    assert all("transcript" not in h for h in hist)


def test_disabled_advisor_returns_a_clean_refusal(monkeypatch):
    monkeypatch.setattr(debate.settings, "ADVISOR_ENABLED", False)
    result = debate.convene("NVDA", force=True)
    assert result["verdict"] is None
    assert result["agents"] == []
    assert "disabled" in result["error"].lower()
