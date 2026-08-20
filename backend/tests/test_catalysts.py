"""The catalyst map: partners, not dates.

    cd backend && .venv/Scripts/python -m pytest tests/test_catalysts.py -q
"""
import os
import time

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import catalysts as c  # noqa: E402


# --------------------------------------------------------------- name hygiene
@pytest.mark.parametrize("raw,want", [
    ("ModernaTX, Inc.", "Moderna"),
    ("Eisai Inc.", "Eisai"),
    ("AstraZeneca", "AstraZeneca"),
    ("Merck Sharp & Dohme LLC", "Merck Sharp & Dohme"),
])
def test_registry_names_reduce_to_something_searchable(raw, want):
    assert c._clean(raw) == want


@pytest.mark.parametrize("name", [
    "National Cancer Institute (NCI)",
    "European Organisation for Research and Treatment of Cancer - EORTC",
    "NCIC Clinical Trials Group",
    "PPD, Part of Thermo Fisher Scientific",
    "Johns Hopkins University",
    "Alzheimer's Association",
])
def test_collaborators_you_cannot_buy_are_excluded(name):
    """A trial partner is only interesting if you can take a position in it.

    Half of Merck's phase-3 collaborators are cooperative groups, universities
    and CROs. A CRO is paid whether the drug works or not — it is a vendor on
    the trial, not leverage on the result.
    """
    assert c.investable(name, exclude=set()) is False


def test_the_sponsor_is_not_its_own_partner():
    assert c.investable("Merck Sharp & Dohme LLC",
                        exclude={"Merck Sharp & Dohme"}) is False


def test_a_real_biotech_partner_survives():
    assert c.investable("ModernaTX, Inc.", exclude={"Merck Sharp & Dohme"}) is True


# ------------------------------------------------------------------ freshness
def _trial(status, pcd):
    return {"status": status, "primary_completion": pcd}


def _ago(days):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))


def _ahead(days):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + days * 86400))


def test_enrolment_closed_with_a_future_endpoint_is_live():
    # This is the state INTerpath-001 was in the morning it moved MRNA 177%.
    assert c._still_live(_trial("ACTIVE_NOT_RECRUITING", _ahead(900))) is True


def test_a_long_past_endpoint_is_history_even_if_still_active():
    """Six Myriad Genetics rows from 2016-2020 topped the list before this.

    ACTIVE_NOT_RECRUITING on a trial whose primary endpoint passed years ago
    means long-term follow-up. Whatever it had to say, it said.
    """
    assert c._still_live(_trial("ACTIVE_NOT_RECRUITING", "2016-09-19")) is False


def test_a_recent_completion_still_counts():
    assert c._still_live(_trial("COMPLETED", _ago(30))) is True


def test_an_old_completion_does_not():
    assert c._still_live(_trial("COMPLETED", "2013-06-17")) is False


def test_recruiting_is_not_a_catalyst():
    # Still enrolling means the readout is not close enough to matter.
    assert c._still_live(_trial("RECRUITING", _ahead(400))) is False


def test_a_missing_date_falls_back_to_the_status():
    assert c._still_live(_trial("ACTIVE_NOT_RECRUITING", None)) is True
    assert c._still_live(_trial("COMPLETED", None)) is False


def test_partial_registry_dates_parse():
    # The registry emits YYYY and YYYY-MM as well as full dates.
    assert c._as_epoch("2028-04") is not None
    assert c._as_epoch("2028") is not None
    assert c._as_epoch("") is None
    assert c._as_epoch(None) is None


# --------------------------------------------------------------------- build
def test_the_map_is_leverage_ranked_and_names_the_partner(monkeypatch):
    """End to end on a stubbed registry: the MRK/MRNA row is the whole point."""
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT05933577", "briefTitle": "V940-001"},
        "statusModule": {
            "overallStatus": "ACTIVE_NOT_RECRUITING",
            "primaryCompletionDateStruct": {"date": _ahead(900)},
            "lastUpdatePostDateStruct": {"date": "2025-09-24"},
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Merck Sharp & Dohme LLC"},
            "collaborators": [{"name": "ModernaTX, Inc."},
                              {"name": "National Cancer Institute (NCI)"}],
        },
        "designModule": {"phases": ["PHASE3"]},
    }}
    monkeypatch.setattr(c, "fetch_trials", lambda *a, **k: [study])
    monkeypatch.setattr(c, "resolve_ticker",
                        lambda n: "MRNA" if "moderna" in n.lower() else None)
    caps = {"MRK": 360e9, "MRNA": 24e9}
    monkeypatch.setattr(c, "market_cap", lambda s: caps.get(s.upper()))

    out = c.build(["MRK", "NVDA"])

    assert out["covered"] == ["MRK"]
    assert out["uncovered"] == ["NVDA"]      # no registry presence is not a miss
    assert len(out["trials"]) == 1
    row = out["trials"][0]
    assert [p["symbol"] for p in row["partners"]] == ["MRNA"]   # NCI dropped
    # 360bn sponsor, 24bn partner: the same news moves the partner 15x harder.
    assert row["partners"][0]["leverage"] == 15.0


def test_a_micro_cap_match_is_dropped_as_a_bad_name_hit(monkeypatch):
    """Canadian Solar was once ranked a 1,065x partner on an antipsychotics
    trial. A cap floor is the backstop behind the stricter name matching."""
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT1", "briefTitle": "t"},
        "statusModule": {"overallStatus": "ACTIVE_NOT_RECRUITING",
                         "primaryCompletionDateStruct": {"date": _ahead(400)}},
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Merck Sharp & Dohme LLC"},
            "collaborators": [{"name": "Tiny Bio"}]},
        "designModule": {"phases": ["PHASE3"]},
    }}
    monkeypatch.setattr(c, "fetch_trials", lambda *a, **k: [study])
    monkeypatch.setattr(c, "resolve_ticker", lambda n: "TINY")
    monkeypatch.setattr(c, "market_cap",
                        lambda s: 360e9 if s.upper() == "MRK" else 5e6)

    assert c.build(["MRK"])["trials"] == []
