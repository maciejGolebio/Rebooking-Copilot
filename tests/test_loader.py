"""Loader: typed fixtures, exact amounts, bad records rejected one by one (D-00c, D-26)."""

import copy
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from rebooking_copilot.loader import IssueCode, LoaderError, load_fare_snapshot, load_pnrs, parse_fare_snapshot, parse_pnrs
from rebooking_copilot.money import Money

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def raw(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(), parse_float=Decimal)


def test_fixture_pnrs_load_typed_and_exact():
    result = load_pnrs(FIXTURES / "pnrs.json")
    assert [p.pnr for p in result.pnrs] == ["QX7T2A", "LM9P4C", "RT5K8B", "ZC3N1D", "HB6W9E"]
    assert result.rejected == []
    lm9 = result.pnrs[1]
    assert lm9.passengers == 2
    assert lm9.ticket.price_per_passenger == Money(amount=Decimal("350.00"), currency="USD")
    assert isinstance(lm9.ticket.total_paid.amount, Decimal)
    seg = lm9.itinerary[0]
    assert seg.departure == datetime(2026, 9, 2, 13, 30)
    assert seg.departure.tzinfo is None  # local time, no offset in the data


def test_fixture_snapshot_loads_with_aware_capture_time():
    snap = load_fare_snapshot(FIXTURES / "fares_feed.json")
    assert snap.captured_at.tzinfo is not None
    assert len(snap.offers) == 6
    assert snap.rejected == []
    of3 = next(o for o in snap.offers if o.offer_id == "OF-3001")
    assert of3.price == Money(amount=Decimal("2100.00"), currency="USD")
    assert of3.route.departure_date == date(2026, 8, 20)


def _pnrs_with(mutate) -> dict:
    data = copy.deepcopy(raw("pnrs.json"))
    mutate(data["pnrs"])
    return data


def _only_rejection(result, locator):
    assert locator not in [p.pnr for p in result.pnrs]
    (rej,) = [r for r in result.rejected if r.pnr == locator]
    return rej


def test_total_not_matching_price_times_pax_is_rejected():
    def mutate(pnrs):
        pnrs[1]["ticket"]["totalPaid"]["amount"] = Decimal("650.00")

    result = parse_pnrs(_pnrs_with(mutate))
    rej = _only_rejection(result, "LM9P4C")
    assert IssueCode.DATA_INCONSISTENT in {i.code for i in rej.issues}


def test_mixed_currencies_within_a_ticket_are_rejected():
    def mutate(pnrs):
        pnrs[0]["ticket"]["changeFeePerPassenger"]["currency"] = "EUR"

    rej = _only_rejection(parse_pnrs(_pnrs_with(mutate)), "QX7T2A")
    assert IssueCode.DATA_INCONSISTENT in {i.code for i in rej.issues}


def test_missing_field_is_rejected_not_defaulted():
    def mutate(pnrs):
        del pnrs[3]["ticket"]["refundable"]

    rej = _only_rejection(parse_pnrs(_pnrs_with(mutate)), "ZC3N1D")
    assert IssueCode.DATA_INVALID in {i.code for i in rej.issues}


@pytest.mark.parametrize(
    "field, value",
    [("passengers", "2"), ("passengers", 0), ("passengers", 2.0), ("passengers", True)],
)
def test_passenger_count_is_not_coerced(field, value):
    def mutate(pnrs):
        pnrs[1][field] = value

    rej = _only_rejection(parse_pnrs(_pnrs_with(mutate)), "LM9P4C")
    assert IssueCode.DATA_INVALID in {i.code for i in rej.issues}


def test_unknown_field_is_rejected():
    def mutate(pnrs):
        pnrs[4]["ticket"]["taxes"] = {"amount": Decimal("12.00"), "currency": "USD"}

    rej = _only_rejection(parse_pnrs(_pnrs_with(mutate)), "HB6W9E")
    assert IssueCode.DATA_INVALID in {i.code for i in rej.issues}


def test_multi_segment_itinerary_is_unsupported():
    def mutate(pnrs):
        pnrs[0]["itinerary"].append(copy.deepcopy(pnrs[0]["itinerary"][0]))

    rej = _only_rejection(parse_pnrs(_pnrs_with(mutate)), "QX7T2A")
    assert {i.code for i in rej.issues} == {IssueCode.UNSUPPORTED_ITINERARY}


def test_every_input_pnr_appears_exactly_once():
    def mutate(pnrs):
        pnrs[0]["passengers"] = -1
        del pnrs[2]["pnr"]  # even without a locator it must be accounted for

    data = _pnrs_with(mutate)
    result = parse_pnrs(data)
    assert len(result.pnrs) + len(result.rejected) == len(data["pnrs"])
    assert sorted(r.index for r in result.rejected) == [0, 2]


def test_invalid_offer_is_excluded_and_reported():
    data = copy.deepcopy(raw("fares_feed.json"))
    data["offers"][1]["price"]["amount"] = 320.0  # a float sneaking in
    data["offers"][5]["seatsAvailable"] = -1
    snap = parse_fare_snapshot(data)
    assert {o.offer_id for o in snap.offers} == {"OF-1001", "OF-3001", "OF-4001", "OF-5001"}
    assert sorted(r.offer_id for r in snap.rejected) == ["OF-2001", "OF-5002"]


def test_offer_route_date_must_match_departure():
    data = copy.deepcopy(raw("fares_feed.json"))
    data["offers"][0]["route"]["departureDate"] = "2026-08-16"
    snap = parse_fare_snapshot(data)
    (rej,) = snap.rejected
    assert rej.offer_id == "OF-1001"
    assert IssueCode.DATA_INCONSISTENT in {i.code for i in rej.issues}


def test_capture_time_without_timezone_is_rejected():
    data = copy.deepcopy(raw("fares_feed.json"))
    data["capturedAt"] = "2026-07-08T09:00:00"
    with pytest.raises(LoaderError):
        parse_fare_snapshot(data)


def test_broken_top_level_structure_raises(tmp_path):
    bad = tmp_path / "pnrs.json"
    bad.write_text('{"bookings": []}')
    with pytest.raises(LoaderError):
        load_pnrs(bad)
