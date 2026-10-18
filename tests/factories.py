"""Test-only builders and spec oracles for the decision slice.

Builders deep-copy the fixture JSON and edit it (like test_loader.py), then go through the real loader, so every
edge case is valid input under D-26. Oracles restate the formulas from the policy.py / decision.py docstrings
(D-10, D-11, D-13, D-14, D-18, D-27); they never call the code under test.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path

from hypothesis import strategies as st

from rebooking_copilot.loader import FareSnapshot, PnrLoad, load_fare_snapshot, load_pnrs, parse_fare_snapshot, parse_pnrs
from rebooking_copilot.models import Offer, Pnr
from rebooking_copilot.money import Money
from rebooking_copilot.policy import PolicyConfig, Reason, SettlementPolicy

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CAPTURED_AT = datetime(2026, 7, 8, 9, 0, tzinfo=UTC)  # fares_feed.json capturedAt
MOCK_USD_EUR = Decimal("0.9276")  # D-27 mock table, EUR per 1 USD

CABIN_ORDER = ("BASIC_ECONOMY", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST")


def usd(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="USD")


def eur(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="EUR")


# --- raw fixture copies -------------------------------------------------------------------------------------------

@cache
def _text(name: str) -> str:
    return (FIXTURES / name).read_text()


def raw(name: str) -> dict:
    """A fresh, independent copy of a fixture file, numbers as Decimal."""
    return json.loads(_text(name), parse_float=Decimal)


def raw_booking(locator: str) -> dict:
    (record,) = [p for p in raw("pnrs.json")["pnrs"] if p["pnr"] == locator]
    return record


def raw_offer(offer_id: str) -> dict:
    (record,) = [o for o in raw("fares_feed.json")["offers"] if o["offerId"] == offer_id]
    return record


def booking(
    locator: str = "QX7T2A",
    *,
    pnr: str | None = None,
    passengers: int | None = None,
    price: str | Decimal | None = None,
    currency: str | None = None,
    fee: str | Decimal | None = None,
    refundable: bool | None = None,
    bags: int | None = None,
    cabin: str | None = None,
) -> dict:
    """A fixture booking with edits; totalPaid is kept equal to price × passengers (D-26)."""
    record = raw_booking(locator)
    ticket = record["ticket"]
    if pnr is not None:
        record["pnr"] = pnr
    if passengers is not None:
        record["passengers"] = passengers
    if price is not None:
        ticket["pricePerPassenger"]["amount"] = Decimal(price)
    if currency is not None:
        for key in ("pricePerPassenger", "totalPaid", "changeFeePerPassenger"):
            ticket[key]["currency"] = currency
    if fee is not None:
        ticket["changeFeePerPassenger"]["amount"] = Decimal(fee)
    if refundable is not None:
        ticket["refundable"] = refundable
    if bags is not None:
        ticket["baggageIncludedPieces"] = bags
    if cabin is not None:
        ticket["cabin"] = cabin
        for segment in record["itinerary"]:
            segment["cabin"] = cabin
    ticket["totalPaid"]["amount"] = ticket["pricePerPassenger"]["amount"] * record["passengers"]
    return record


def offer(
    base_id: str,
    *,
    offer_id: str | None = None,
    price: str | Decimal | None = None,
    currency: str | None = None,
    refundable: bool | None = None,
    bags: int | None = None,
    seats: int | None = None,
    cabin: str | None = None,
    stops: int | None = None,
    carrier: str | None = None,
    flight_number: str | None = None,
    shift_minutes: int = 0,
    later_day: bool = False,
    fare_basis: str | None = None,
    fee: str | Decimal | None = None,
) -> dict:
    """A fixture offer with edits. `shift_minutes` moves departure and arrival; `later_day` adds a day to arrival."""
    record = raw_offer(base_id)
    if offer_id is not None:
        record["offerId"] = offer_id
    if price is not None:
        record["price"]["amount"] = Decimal(price)
    if currency is not None:
        record["price"]["currency"] = currency
        record["changeFeePerPassenger"]["currency"] = currency
    if fee is not None:
        record["changeFeePerPassenger"]["amount"] = Decimal(fee)
    for key, value in (
        ("refundable", refundable), ("baggageIncludedPieces", bags), ("seatsAvailable", seats), ("cabin", cabin),
        ("stops", stops), ("carrier", carrier), ("flightNumber", flight_number), ("fareBasis", fare_basis),
    ):
        if value is not None:
            record[key] = value
    if shift_minutes or later_day:
        departure = datetime.fromisoformat(record["departure"]) + timedelta(minutes=shift_minutes)
        arrival = datetime.fromisoformat(record["arrival"]) + timedelta(minutes=shift_minutes, days=1 if later_day else 0)
        record["departure"] = departure.isoformat()
        record["arrival"] = arrival.isoformat()
        record["route"]["departureDate"] = departure.date().isoformat()
    return record


# --- typed inputs -------------------------------------------------------------------------------------------------

def load(bookings: list[dict], offers: list[dict], *, captured_at: str = "2026-07-08T09:00:00Z", allow_rejected: bool = False) -> tuple[PnrLoad, FareSnapshot]:
    pnr_load = parse_pnrs({"pnrs": bookings})
    snapshot = parse_fare_snapshot({"capturedAt": captured_at, "offers": offers})
    if not allow_rejected:
        assert pnr_load.rejected == (), f"test data must be valid: {pnr_load.rejected}"
    assert snapshot.rejected == (), f"test data must be valid: {snapshot.rejected}"
    return pnr_load, snapshot


def fixture_inputs() -> tuple[PnrLoad, FareSnapshot]:
    return load_pnrs(FIXTURES / "pnrs.json"), load_fare_snapshot(FIXTURES / "fares_feed.json")


def pnr_model(record: dict) -> Pnr:
    (pnr,) = load([record], [])[0].pnrs
    return pnr


def offer_model(record: dict) -> Offer:
    (model,) = load([], [record])[1].offers
    return model


def fixture_pnr(locator: str) -> Pnr:
    return pnr_model(raw_booking(locator))


def fixture_offer(offer_id: str) -> Offer:
    return offer_model(raw_offer(offer_id))


# --- spec oracles (formulas restated from the docstrings; never the code under test) ------------------------------

def spec_money(pnr: Pnr, offer_: Offer, policy: PolicyConfig, rates: dict[tuple[str, str], Decimal]) -> dict | None:
    """policy.py docstring (D-18, D-10, D-13, D-27). None when no FX rate exists (CURRENCY_MISMATCH_NO_FX)."""
    ticket = pnr.ticket
    ticket_ccy, offer_ccy = ticket.price_per_passenger.currency, offer_.price.currency
    if offer_ccy == ticket_ccy:
        rate = Decimal(1)
    elif (offer_ccy, ticket_ccy) in rates:
        rate = rates[(offer_ccy, ticket_ccy)]
    else:
        return None
    pax = pnr.passengers
    offer_tc = offer_.price.amount * rate
    gross = (ticket.price_per_passenger.amount - offer_tc) * pax
    fees = ticket.change_fee_per_passenger.amount * pax  # the EXISTING ticket's fee (D-18)
    net = gross - fees
    credit = not ticket.refundable  # D-10 assumption
    if credit and policy.settlement_policy is SettlementPolicy.CREDIT_DISCOUNTED:
        counted = gross * policy.credit_discount_factor - fees
    else:
        counted = net
    threshold = max(policy.min_net_absolute, policy.min_net_fraction * ticket.total_paid.amount)
    return {
        "currency": ticket_ccy, "offer_tc": offer_tc, "gross": gross, "fees": fees, "net": net,
        "settlement": "CREDIT" if credit else "CASH", "counted": counted, "threshold": threshold, "fx_used": offer_ccy != ticket_ccy,
    }


def spec_shift_minutes(pnr: Pnr, offer_: Offer) -> int:
    delta = offer_.departure - pnr.itinerary[0].departure
    return int(delta.total_seconds() // 60)


def spec_hard_blocks(pnr: Pnr, offer_: Offer, policy: PolicyConfig, rates: dict[tuple[str, str], Decimal]) -> set[Reason]:
    """D-11, D-13, D-14, D-27: the INELIGIBLE reasons the policy docstring lists (before the seat ledger)."""
    segment, ticket = pnr.itinerary[0], pnr.ticket
    blocks: set[Reason] = set()
    if offer_.baggage_included_pieces < ticket.baggage_included_pieces:
        blocks.add(Reason.FEWER_BAGS)
    if abs(spec_shift_minutes(pnr, offer_)) > policy.schedule_window.total_seconds() / 60:
        blocks.add(Reason.SCHEDULE_OUTSIDE_WINDOW)
    if offer_.arrival.date() > segment.arrival.date():
        blocks.add(Reason.ARRIVES_LATER_DAY)
    if offer_.seats_available < pnr.passengers:
        blocks.add(Reason.INSUFFICIENT_SEATS)
    money = spec_money(pnr, offer_, policy, rates)
    if money is None:
        blocks.add(Reason.CURRENCY_MISMATCH_NO_FX)
    elif money["counted"] < money["threshold"]:
        blocks.add(Reason.NET_SAVING_BELOW_THRESHOLD)
    return blocks


def spec_review_reasons(pnr: Pnr, offer_: Offer, policy: PolicyConfig, rates: dict[tuple[str, str], Decimal] | None = None) -> tuple[set[Reason], set[Reason]]:
    """(required, allowed) review-level reasons. DIFFERENT_FLIGHT is only *allowed* when the carrier also changed,
    because the spec doesn't say whether a carrier change also counts as a different flight. PRICE_ANOMALY (D-34) is
    required when the offer, in the ticket currency, is below paid × (1 − max plausible discount); not evaluated without FX."""
    segment, ticket = pnr.itinerary[0], pnr.ticket
    required: set[Reason] = set()
    allowed: set[Reason] = set()
    if CABIN_ORDER.index(offer_.cabin) < CABIN_ORDER.index(ticket.cabin):
        required.add(Reason.CABIN_DOWNGRADE)
    if ticket.refundable and not offer_.refundable:
        required.add(Reason.REFUNDABILITY_LOST)
    if offer_.carrier != segment.carrier:
        required.add(Reason.CARRIER_CHANGE)
    if offer_.stops > segment.stops:
        required.add(Reason.ADDED_STOP)
    within_window = abs(spec_shift_minutes(pnr, offer_)) <= policy.schedule_window.total_seconds() / 60
    different_flight = (offer_.carrier, offer_.flight_number) != (segment.carrier, segment.flight_number)
    if different_flight and within_window:
        (allowed if offer_.carrier != segment.carrier else required).add(Reason.DIFFERENT_FLIGHT)
    money = spec_money(pnr, offer_, policy, {("USD", "EUR"): MOCK_USD_EUR} if rates is None else rates)
    if money is not None and money["offer_tc"] < ticket.price_per_passenger.amount * (1 - policy.max_plausible_discount):
        required.add(Reason.PRICE_ANOMALY)
    return required, required | allowed


# --- hypothesis strategies (hypothesis is a recorded dev dependency, D-03/D-04) -----------------------------------
# Generated data stays on QX7T2A's route and date (JFK→LAX 2026-08-15, AA118 08:00); departure shifts of ±120 min keep
# the date, so every generated offer is a candidate. A different flight always gets a different flight number.

@st.composite
def booking_records(draw) -> dict:
    return booking(
        "QX7T2A",
        passengers=draw(st.integers(1, 3)),
        price=draw(st.decimals(min_value=Decimal("50"), max_value=Decimal("900"), places=2)),
        currency=draw(st.sampled_from(["USD", "EUR"])),
        fee=draw(st.decimals(min_value=Decimal("0"), max_value=Decimal("200"), places=2)),
        refundable=draw(st.booleans()),
        bags=draw(st.integers(0, 2)),
        cabin=draw(st.sampled_from(CABIN_ORDER)),
    )


@st.composite
def offer_records(draw, offer_id: str = "OF-GEN") -> dict:
    if draw(st.booleans()):
        flight = dict(carrier="AA", flight_number="AA118", shift_minutes=0)
    else:
        carrier = draw(st.sampled_from(["AA", "B6"]))
        flight = dict(carrier=carrier, flight_number=f"{carrier}{draw(st.integers(200, 999))}", shift_minutes=draw(st.integers(-120, 120)))
    return offer(
        "OF-1001",
        offer_id=offer_id,
        price=draw(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000"), places=2)),  # > 0 (D-35)
        currency=draw(st.sampled_from(["USD", "USD", "EUR"])),  # USD→EUR converts; EUR→USD has no mock rate
        refundable=draw(st.booleans()),
        bags=draw(st.integers(0, 2)),
        seats=draw(st.integers(0, 4)),
        cabin=draw(st.sampled_from(CABIN_ORDER)),
        stops=draw(st.integers(0, 1)),
        later_day=draw(st.sampled_from([False, False, False, True])),
        fee=draw(st.decimals(min_value=Decimal("0"), max_value=Decimal("200"), places=2)),
        **flight,
    )


@st.composite
def policies(draw) -> PolicyConfig:
    return PolicyConfig(
        settlement_policy=draw(st.sampled_from(list(SettlementPolicy))),
        credit_discount_factor=draw(st.sampled_from([Decimal("0.5"), Decimal("0.7"), Decimal("1")])),
        schedule_window=timedelta(minutes=draw(st.sampled_from([30, 60, 90]))),
    )


@st.composite
def scenarios(draw, max_offers: int = 3) -> tuple[dict, list[dict], PolicyConfig]:
    """One booking, 1..max_offers candidate offers with distinct ids, and a policy."""
    count = draw(st.integers(1, max_offers))
    offers = [draw(offer_records(offer_id=f"OF-9{i:03d}")) for i in range(count)]
    return draw(booking_records()), offers, draw(policies())


def assert_breakdown_recomputable(breakdown, pnr: Pnr, policy: PolicyConfig) -> None:
    """money-safety invariant 1: every number in the breakdown follows from the inputs and the other fields."""
    ticket = pnr.ticket
    ccy = ticket.price_per_passenger.currency
    pax = pnr.passengers
    assert breakdown.passengers == pax
    assert breakdown.paid_per_passenger == ticket.price_per_passenger
    for field in ("offer_price_per_passenger_in_ticket_currency", "gross_saving", "change_fees", "net_saving", "counted_net_saving", "threshold"):
        assert getattr(breakdown, field).currency == ccy, field
    if breakdown.fx is None:
        assert breakdown.offer_price_per_passenger_in_ticket_currency == breakdown.offer_price_per_passenger
    else:
        assert breakdown.fx.from_currency == breakdown.offer_price_per_passenger.currency
        assert breakdown.fx.to_currency == ccy
        assert breakdown.offer_price_per_passenger_in_ticket_currency.amount == breakdown.offer_price_per_passenger.amount * breakdown.fx.rate
    assert breakdown.gross_saving.amount == (breakdown.paid_per_passenger.amount - breakdown.offer_price_per_passenger_in_ticket_currency.amount) * pax
    assert breakdown.change_fees.amount == ticket.change_fee_per_passenger.amount * pax
    assert breakdown.net_saving.amount == breakdown.gross_saving.amount - breakdown.change_fees.amount
    assert breakdown.settlement == ("CASH" if ticket.refundable else "CREDIT")
    if breakdown.settlement == "CREDIT" and policy.settlement_policy is SettlementPolicy.CREDIT_DISCOUNTED:
        assert breakdown.counted_net_saving.amount == breakdown.gross_saving.amount * policy.credit_discount_factor - breakdown.change_fees.amount
    else:
        assert breakdown.counted_net_saving == breakdown.net_saving
    assert breakdown.threshold.amount == max(policy.min_net_absolute, policy.min_net_fraction * ticket.total_paid.amount)
