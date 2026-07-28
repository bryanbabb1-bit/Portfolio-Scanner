"""Clean Sheet tests. The load-bearing one is that the build is actually blind.

    cd backend && .venv/Scripts/python -m pytest tests/test_cleansheet.py -q
"""
import json
import os

os.environ["DATA_MODE"] = "mock"

import pytest  # noqa: E402

from app.services import advisor, cleansheet, discovery  # noqa: E402
from app.services import portfolio as pf_service  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cleansheet, "_FILE", tmp_path / "cleansheet.json")
    monkeypatch.setattr(cleansheet.settings, "ADVISOR_ENABLED", True)
    yield


REPLY = {
    "thesis": "Quality compounders across a few uncorrelated engines.",
    "allocation": [
        {"theme": "AI Infrastructure", "pct": 30, "why": "Secular demand."},
        {"theme": "Healthcare", "pct": 25, "why": "Cheap and defensive."},
        {"theme": "Financials", "pct": 25, "why": "Rate-cycle leverage."},
        {"theme": "Broad Market", "pct": 20, "why": "Ballast."},
    ],
    "picks": [
        {"symbol": "NVDA", "theme": "AI Infrastructure", "pct": 30, "why": "Leader."},
        {"symbol": "LLY", "theme": "Healthcare", "pct": 25, "why": "Pipeline."},
        {"symbol": "JPM", "theme": "Financials", "pct": 25, "why": "Best in class."},
        {"symbol": "VOO", "theme": "Broad Market", "pct": 20, "why": "Ballast."},
    ],
    "avoided": ["Skipped miners — balance sheets too weak."],
}


def _stub(monkeypatch, reply=REPLY):
    seen = {}

    def fake(prompt, resume=None, research=False, model=None):
        seen["prompt"] = prompt
        return json.dumps(reply), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    return seen


# ------------------------------------------------------- THE blindness contract
def test_build_prompt_is_invariant_to_what_the_client_holds(monkeypatch):
    """THE load-bearing test. If holdings reach the construction prompt the
    exercise is theatre — the model would re-describe the book back at us.

    Asserted as an invariance rather than a substring scan: the prompt for a
    100% semis book and for a 100% healthcare book must be byte-identical.
    Substring matching gave a false positive here, because "holdings" appears
    legitimately in the persona and in names like "Arm Holdings".
    """
    def book(*symbols):
        return {
            "holdings": [{"symbol": s, "shares": 10, "cost_basis": 100}
                         for s in symbols],
            "watchlist": [], "cash": 0, "themes": {},
        }

    monkeypatch.setattr(pf_service, "load_portfolio", lambda: book("NVDA", "AMD", "TSM"))
    a = cleansheet.build_prompt({"horizon": "2 years"}, 10_000.0)

    monkeypatch.setattr(pf_service, "load_portfolio", lambda: book("LLY", "JNJ", "PFE"))
    b = cleansheet.build_prompt({"horizon": "2 years"}, 10_000.0)

    assert a == b, "the clean-sheet prompt changed with the holdings — it is not blind"
    assert "NOT been told what they currently own" in a


def test_build_prompt_carries_no_position_economics():
    """Equity (how much to invest) is legitimate. Cost basis and P/L are not —
    they can only come from the existing book."""
    prompt = cleansheet.build_prompt({"horizon": "2 years"}, 10_000.0).lower()
    # "currently own" is deliberately absent from this list: the instruction
    # itself says "NOT been told what they currently own".
    for banned in ("cost basis", "unrealized", "p/l ", "current allocation",
                   "standing call", "shares"):
        assert banned not in prompt, banned


def test_build_prompt_offers_the_full_theme_vocabulary():
    prompt = cleansheet.build_prompt({}, 10_000.0)
    for theme in ("Healthcare", "Financials", "Industrials", "Broad Market"):
        assert theme in prompt


def test_candidates_include_owned_names_unmarked(monkeypatch):
    """The menu must be able to contain what the client owns — otherwise the
    from-scratch book can never overlap and the metric is rigged to zero."""
    calls = {}
    real = discovery.discover

    def spy(min_score=0.0, limit=24, include_owned=False):
        calls["include_owned"] = include_owned
        return real(min_score=min_score, limit=limit, include_owned=include_owned)

    monkeypatch.setattr(discovery, "discover", spy)
    cleansheet._candidate_block()
    assert calls["include_owned"] is True


# ------------------------------------------------------------------- the diff
def test_overlap_is_weighted_not_counted(monkeypatch):
    """Agreeing on a 1% position is not the same as agreeing on a 30% one."""
    monkeypatch.setattr(cleansheet, "_current_allocation",
                        lambda: ({"AI Infrastructure": 100.0}, {"NVDA": 100.0}, 9_000.0))
    d = cleansheet._diff(REPLY["allocation"], REPLY["picks"])
    assert d["overlap_pct"] == 30      # NVDA's weight
    assert d["name_overlap_pct"] == 25  # 1 of 4 names
    assert d["held_picks"] == ["NVDA"]
    assert set(d["new_picks"]) == {"LLY", "JPM", "VOO"}


def test_blind_spots_are_themes_wanted_but_not_owned(monkeypatch):
    monkeypatch.setattr(cleansheet, "_current_allocation",
                        lambda: ({"AI Infrastructure": 100.0}, {"NVDA": 100.0}, 9_000.0))
    d = cleansheet._diff(REPLY["allocation"], REPLY["picks"])
    spots = {r["theme"] for r in d["blind_spots"]}
    assert spots == {"Healthcare", "Financials", "Broad Market"}


def test_overweight_flags_where_the_book_is_heavier_than_the_build(monkeypatch):
    monkeypatch.setattr(cleansheet, "_current_allocation",
                        lambda: ({"AI Infrastructure": 100.0}, {"NVDA": 100.0}, 9_000.0))
    d = cleansheet._diff(REPLY["allocation"], REPLY["picks"])
    assert [r["theme"] for r in d["overweight"]] == ["AI Infrastructure"]
    assert d["overweight"][0]["delta"] == -70.0


def test_a_book_matching_the_build_reads_aligned(monkeypatch):
    monkeypatch.setattr(
        cleansheet, "_current_allocation",
        lambda: ({"AI Infrastructure": 30.0, "Healthcare": 25.0,
                  "Financials": 25.0, "Broad Market": 20.0},
                 {"NVDA": 30.0, "LLY": 25.0, "JPM": 25.0, "VOO": 20.0}, 9_000.0))
    d = cleansheet._diff(REPLY["allocation"], REPLY["picks"])
    verdict, headline = cleansheet._verdict(d)
    assert d["overlap_pct"] == 100
    assert verdict == "ALIGNED"
    assert "conviction" in headline


def test_a_completely_different_book_reads_divergent(monkeypatch):
    monkeypatch.setattr(cleansheet, "_current_allocation",
                        lambda: ({"Compute Power": 100.0}, {"RIOT": 100.0}, 9_000.0))
    d = cleansheet._diff(REPLY["allocation"], REPLY["picks"])
    verdict, _ = cleansheet._verdict(d)
    assert d["overlap_pct"] == 0
    assert verdict == "DIVERGENT"


# ------------------------------------------------------------------ end to end
def test_build_returns_a_full_result(monkeypatch):
    seen = _stub(monkeypatch)
    r = cleansheet.build(force=True)
    assert r["engine"] == "claude"
    assert len(r["picks"]) == 4
    assert r["verdict"] in {"ALIGNED", "PARTIAL", "DIVERGENT"}
    assert r["diff"]["overlap_pct"] is not None
    assert "Built blind" in r["method"]
    assert "NOT been told" in seen["prompt"]


def test_cache_prevents_a_second_model_call(monkeypatch):
    calls = []

    def fake(prompt, resume=None, research=False, model=None):
        calls.append(1)
        return json.dumps(REPLY), "sid"

    monkeypatch.setattr(advisor, "_run_claude", fake)
    cleansheet.build(force=True)
    cleansheet.build()                     # cached
    assert len(calls) == 1
    cleansheet.build(force=True)
    assert len(calls) == 2


def test_unreachable_desk_degrades_cleanly(monkeypatch):
    monkeypatch.setattr(advisor, "_run_claude",
                        lambda *a, **k: (None, None))
    r = cleansheet.build(force=True)
    assert r["engine"] == "unavailable"
    assert r["picks"] == []
    assert r["error"]


def test_disabled_advisor_is_refused_not_faked(monkeypatch):
    monkeypatch.setattr(cleansheet.settings, "ADVISOR_ENABLED", False)
    r = cleansheet.build(force=True)
    assert r["engine"] == "disabled"
    assert r["diff"] is None
