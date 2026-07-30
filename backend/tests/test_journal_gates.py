"""The two ways a bad read used to become a fake trade, and the GEV loop.

1. A decimal point going missing inside ONE position. On 2026-07-29 NVDA's
   shares read as 898497 instead of 8.98497; the diff booked an 898,489-share
   buy and then an 898,488-share sell for -$11,779,177.88 of phantom realized
   loss and a reported total return of -117,299%. The existing gate only
   watched the NUMBER of holdings, which never changed.
2. A closed position leaving its instructions behind, so the brief kept
   reissuing "Sell all $152 GEV" days after the position was gone.
"""
from __future__ import annotations

import json

import pytest

from app.services import journal, pins, stance


def _snap(mapping: dict[str, tuple[float, float]]) -> None:
    """Seed the baseline snapshot."""
    journal._SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(journal._SNAPSHOT_FILE, "w") as f:
        json.dump({s: {"shares": sh, "cost": c} for s, (sh, c) in mapping.items()}, f)


def _holdings(mapping: dict[str, tuple[float, float]]) -> list[dict]:
    return [{"symbol": s, "shares": sh, "cost_basis": c} for s, (sh, c) in mapping.items()]


BOOK = {"NVDA": (8.98497, 203.12), "MSFT": (1.00032, 408.78), "AAPL": (1.95109, 307.74)}


@pytest.fixture(autouse=True)
def _no_live_prices(monkeypatch):
    # _sale_price would otherwise reach for a quote; these tests are about the
    # gate, not pricing.
    monkeypatch.setattr(journal, "_sale_price", lambda sym: 190.0)


def test_missing_decimal_point_is_not_a_trade():
    _snap(BOOK)
    corrupt = dict(BOOK)
    corrupt["NVDA"] = (898497.0, 203.12)     # 8.98497 with the dot gone

    assert journal.snapshot_and_diff(_holdings(corrupt)) == []
    # The baseline must NOT be overwritten, or the next good read books the
    # reverse as an 898,488-share sell.
    with open(journal._SNAPSHOT_FILE) as f:
        assert json.load(f)["NVDA"]["shares"] == pytest.approx(8.98497)


def test_the_reverse_direction_is_caught_too():
    _snap({**BOOK, "NVDA": (898497.0, 203.12)})
    assert journal.snapshot_and_diff(_holdings(BOOK)) == []


def test_a_real_add_still_journals():
    _snap(BOOK)
    grown = dict(BOOK)
    grown["NVDA"] = (10.98497, 203.12)       # bought two more shares

    entries = journal.snapshot_and_diff(_holdings(grown))
    assert [(e["symbol"], e["action"]) for e in entries] == [("NVDA", "buy")]


def test_a_real_close_still_journals_and_books_realized():
    _snap(BOOK)
    without = {k: v for k, v in BOOK.items() if k != "AAPL"}

    entries = journal.snapshot_and_diff(_holdings(without))
    sells = [e for e in entries if e["action"] == "sell"]
    assert [e["symbol"] for e in sells] == ["AAPL"]
    assert sells[0]["realized_pl"] is not None


def test_float_dust_is_still_ignored():
    _snap(BOOK)
    dusty = dict(BOOK)
    dusty["NVDA"] = (8.98499, 203.12)
    assert journal.snapshot_and_diff(_holdings(dusty)) == []


def test_empty_read_gate_still_holds():
    _snap(BOOK)
    assert journal.snapshot_and_diff([]) == []


# ------------------------------------------------------ standing down on close
def test_closing_a_position_retires_its_exit_pins_and_stance():
    _snap({**BOOK, "GEV": (0.16391, 1012.69)})
    pins.add(None, "brief", "Sell all $152 GEV at market (when GEV closes green)")
    pins.add(None, "brief", "Buy $150 VRT near $243 (when GEV proceeds settle)")
    pins.add(None, "brief", "Buy $110 MRK at $131.84")
    stance.set_stance("GEV", "SELL", headline="Wind is the weak link")

    journal.snapshot_and_diff(_holdings(BOOK))   # GEV is gone

    open_texts = [p["text"] for p in pins.list_pins() if p["status"] == "open"]
    # The instruction to exit GEV stands down...
    assert not any("Sell all $152 GEV" in t for t in open_texts)
    # ...but the VRT buy that was WAITING on GEV proceeds survives: its subject
    # is VRT and the GEV clause is a precondition that just came true.
    assert any("Buy $150 VRT" in t for t in open_texts)
    assert any("Buy $110 MRK" in t for t in open_texts)
    assert stance.get("GEV") is None


def test_retirement_is_recorded_as_stood_down_not_as_user_action():
    pins.add(None, "brief", "Sell all GEV at market")
    before = len(journal.list_entries(3650))

    pins.retire_for_symbol("GEV")

    retired = [p for p in pins.list_pins() if p["status"] == "done"]
    assert retired and retired[0]["retired_reason"]
    # It must not claim the client worked a checklist they never touched.
    assert len(journal.list_entries(3650)) == before


def test_retirement_needs_an_exit_verb():
    # A pin that merely mentions the ticker is not an instruction to exit it.
    pins.add(None, "brief", "GEV earnings are Thursday, watch the print")
    assert pins.retire_for_symbol("GEV") == []
    assert [p["status"] for p in pins.list_pins()] == ["open"]


def test_pin_tagged_with_the_symbol_is_retired_regardless_of_wording():
    pins.add("GEV", "ask", "Get out of this one")
    assert len(pins.retire_for_symbol("GEV")) == 1


def test_a_ticker_in_the_subject_slot_blocks_retirement():
    # This pin is about SPMO. Reading past it to find GEV would cancel a live
    # order, so an unrecognised subject blocks retirement.
    pins.add(None, "brief", "Sell SPMO once GEV proceeds land")
    assert pins.retire_for_symbol("GEV") == []
