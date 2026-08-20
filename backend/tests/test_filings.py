"""Material-event filings: the catalyst feed that covers the whole book.

    cd backend && .venv/Scripts/python -m pytest tests/test_filings.py -q
"""
import os
import time

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

import pytest  # noqa: E402

from app.services import filings as f  # noqa: E402


# -------------------------------------------------------------------- ticker
def test_the_books_ticker_style_is_translated_to_the_secs():
    # The book writes BRK.B, the SEC writes BRK-B. One character, no filings.
    assert f._norm("BRK.B") == "BRK-B"
    assert f._norm("nvda") == "NVDA"


# ------------------------------------------------------------------ severity
def test_a_merger_outranks_an_annual_meeting():
    _, merger = f._classify("8-K", "2.01")
    _, meeting = f._classify("8-K", "5.07")
    assert merger == "high"
    assert meeting == "routine"


def test_severity_takes_the_most_serious_item_on_the_filing():
    """One filing, three items: it is as important as its most important part."""
    labels, sev = f._classify("8-K", "5.07,1.01,9.01")
    assert sev == "high"
    assert "Signed a material agreement" in labels


def test_boilerplate_is_dropped_once_there_is_real_news():
    """Item 9.01 rides along on nearly every 8-K and says nothing."""
    labels, _ = f._classify("8-K", "1.01,9.01")
    assert labels == ["Signed a material agreement"]


def test_a_filing_that_is_only_boilerplate_still_says_something():
    labels, sev = f._classify("8-K", "9.01")
    assert labels == ["Financial statements and exhibits"]
    assert sev == "routine"


def test_an_unknown_item_code_is_not_silently_dropped():
    labels, sev = f._classify("8-K", "1.99")
    assert labels == ["Item 1.99"]
    assert sev == "medium"          # unknown means unjudged, not unimportant


def test_forms_that_are_not_8ks_still_matter():
    # An activist stake and a priced offering both move a stock, neither is 8-K.
    assert f._classify("SC 13D", "")[1] == "high"
    assert f._classify("424B5", "")[1] == "high"


# --------------------------------------------------------------------- build
def _submissions(rows):
    return {
        "name": "TEST CORP",
        "filings": {"recent": {
            "form": [r[0] for r in rows],
            "filingDate": [r[1] for r in rows],
            "items": [r[2] for r in rows],
            "accessionNumber": [r[3] for r in rows],
        }},
    }


def _today(offset=0):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - offset * 86400))


@pytest.fixture
def stub(monkeypatch, tmp_path):
    monkeypatch.setattr(f, "_FILE", tmp_path / "filings.json")
    monkeypatch.setattr(f, "_CIK_FILE", tmp_path / "ciks.json")
    monkeypatch.setattr(f, "cik_for", lambda s: "0000000001")
    monkeypatch.setattr(f, "REQUEST_GAP", 0)
    yield


def test_only_material_forms_survive(stub, monkeypatch):
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(1), "1.01", "0001-24-000001"),
        ("4", _today(1), "", "0001-24-000002"),        # insider form, not news
        ("13F-HR", _today(2), "", "0001-24-000003"),   # someone else's holdings
    ]))
    out = f.build(["TEST"])
    assert [r["form"] for r in out["filings"]] == ["8-K"]


def test_filings_outside_the_window_are_dropped(stub, monkeypatch):
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(2), "1.01", "a"),
        ("8-K", _today(90), "1.01", "b"),
    ]))
    assert len(f.build(["TEST"], days=30)["filings"]) == 1


def test_the_important_filing_sorts_above_the_paperwork_same_day(stub, monkeypatch):
    day = _today(1)
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", day, "5.07", "routine-one"),
        ("8-K", day, "2.01", "merger-one"),
    ]))
    out = f.build(["TEST"])
    assert out["filings"][0]["accession"] == "merger-one"


def test_a_symbol_with_no_cik_is_reported_not_silently_skipped(stub, monkeypatch):
    monkeypatch.setattr(f, "cik_for", lambda s: None)
    out = f.build(["NOSUCH"])
    assert out["no_cik"] == ["NOSUCH"]


# --------------------------------------------------------------------- push
def test_the_first_run_does_not_push_the_whole_backlog(stub, monkeypatch):
    """Thirty days of history arriving as thirty notifications is how a
    notification channel gets muted, and a muted channel cannot deliver the
    one that counts."""
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(1), "2.01", "a"),
        ("8-K", _today(2), "1.01", "b"),
    ]))
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda *a, **k: sent.append(a) or {})
    f.get(force=True, symbols=["TEST"])
    assert sent == []


def test_a_new_material_filing_pushes_once(stub, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda *a, **k: sent.append(a[0]) or {})

    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(2), "1.01", "old"),
    ]))
    f.get(force=True, symbols=["TEST"])          # seeds the baseline
    assert sent == []

    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(0), "2.01", "new"),
        ("8-K", _today(2), "1.01", "old"),
    ]))
    f.get(force=True, symbols=["TEST"])
    assert len(sent) == 1 and "TEST" in sent[0]

    f.get(force=True, symbols=["TEST"])          # same filing, no second buzz
    assert len(sent) == 1


def test_routine_filings_never_push(stub, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.push.send",
                        lambda *a, **k: sent.append(a) or {})
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(2), "1.01", "seed"),
    ]))
    f.get(force=True, symbols=["TEST"])
    monkeypatch.setattr(f, "_get", lambda url: _submissions([
        ("8-K", _today(0), "5.07", "vote"),      # annual meeting results
        ("8-K", _today(2), "1.01", "seed"),
    ]))
    f.get(force=True, symbols=["TEST"])
    assert sent == []
