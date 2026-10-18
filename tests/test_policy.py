"""Policy v1: candidate matching, the money breakdown and eligibility tiers (ADR-0005, ADR-0006).

Expected numbers come from the formulas in the policy.py docstring; each is written out next to its case.
Fixture values: tests/factories.py loads fixtures/*.json read-only.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings

from factories import (
    CAPTURED_AT, MOCK_USD_EUR, booking, booking_records, eur, fixture_offer, fixture_pnr, offer, offer_model, offer_records,
    pnr_model, policies, raw, spec_hard_blocks, spec_review_reasons, usd,
)
from rebooking_copilot.fx import FxQuote, FxUnavailableError, MockFxProvider
from rebooking_copilot.models import Offer
from rebooking_copilot.policy import (
    HARD_BLOCKS, REVIEW_LEVEL_REASONS, PolicyConfig, Reason, Settlement, SettlementPolicy, Tier, assess, check_policy,
    compute_saving, find_candidates,
)

AS_OF = CAPTURED_AT
FX = MockFxProvider()
NO_FX = MockFxProvider(rates={})
DEFAULT_RATES = {("USD", "EUR"): MOCK_USD_EUR}


def fixture_offers() -> tuple[Offer, ...]:
    return tuple(offer_model(o) for o in raw("fares_feed.json")["offers"])


def assess_records(booking_record: dict, offer_record: dict, *, policy: PolicyConfig = PolicyConfig(), fx=FX):
    return assess(pnr_model(booking_record), offer_model(offer_record), fx=fx, as_of=AS_OF, policy=policy)


# --- find_candidates ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "locator, expected",
    [
        ("QX7T2A", ("OF-1001",)),
        ("LM9P4C", ("OF-2001",)),
        ("RT5K8B", ("OF-3001",)),
        ("ZC3N1D", ("OF-4001",)),
        ("HB6W9E", ("OF-5001", "OF-5002")),
    ],
)
def test_fixture_candidates_match_on_origin_destination_and_date(locator, expected):
    assert tuple(o.offer_id for o in find_candidates(fixture_pnr(locator), fixture_offers())) == expected


def test_candidates_keep_input_order():
    offers = tuple(reversed(fixture_offers()))
    assert tuple(o.offer_id for o in find_candidates(fixture_pnr("HB6W9E"), offers)) == ("OF-5002", "OF-5001")


def _route_variant(offer_id: str, **route) -> dict:
    record = offer("OF-1001", offer_id=offer_id)
    record["route"].update(route)
    return record


@pytest.mark.parametrize(
    "record",
    [
        offer("OF-1001", offer_id="OF-DAY", shift_minutes=-24 * 60),  # 2026-08-14, one day earlier
        offer("OF-1001", offer_id="OF-NXT", shift_minutes=24 * 60),  # 2026-08-16
        _route_variant("OF-ORG", origin="EWR"),
        _route_variant("OF-DST", destination="SFO"),
        _route_variant("OF-REV", origin="LAX", destination="JFK"),
    ],
    ids=["day-before", "day-after", "other-origin", "other-destination", "reverse-direction"],
)
def test_non_matching_offers_are_not_candidates(record):
    assert find_candidates(fixture_pnr("QX7T2A"), (offer_model(record),)) == ()


def test_matching_ignores_time_of_day_carrier_cabin_and_price():
    # Same O&D and date is all that matching requires; everything else is the policy's job.
    other = offer_model(
        offer("OF-1001", offer_id="OF-ANY", shift_minutes=600, carrier="B6", flight_number="B6999", cabin="FIRST", price="9999.00")
    )
    assert find_candidates(fixture_pnr("QX7T2A"), (other,)) == (other,)


def test_no_offers_no_candidates():
    assert find_candidates(fixture_pnr("QX7T2A"), ()) == ()


# --- compute_saving: fixture breakdowns ---------------------------------------------------------------------------
# gross = (paid pp − offer pp in ticket ccy) × pax · fees = ticket fee pp × pax (D-18) · net = gross − fees
# settlement = CASH if ticket refundable else CREDIT (D-10) · threshold = max(25, 5% × totalPaid) (D-13)

FIXTURE_BREAKDOWNS = {
    # QX7T2A/OF-1001: (480 − 300) × 1 = 180; fees 100 × 1; net 80; non-refundable → CREDIT; max(25, 24) = 25
    ("QX7T2A", "OF-1001"): dict(pax=1, gross=usd("180"), fees=usd("100"), net=usd("80"), settlement=Settlement.CREDIT, threshold=usd("25")),
    # LM9P4C/OF-2001: (350 − 320) × 2 = 60; fees 75 × 2 = 150; net −90; max(25, 5% × 700 = 35) = 35
    ("LM9P4C", "OF-2001"): dict(pax=2, gross=usd("60"), fees=usd("150"), net=usd("-90"), settlement=Settlement.CREDIT, threshold=usd("35")),
    # RT5K8B/OF-3001 (D-27): 2100 USD × 0.9276 = 1947.96 EUR; 2200 − 1947.96 = 252.04; fees 0 EUR; refundable → CASH;
    # max(25, 5% × 2200 = 110) = 110 EUR
    ("RT5K8B", "OF-3001"): dict(pax=1, gross=eur("252.04"), fees=eur("0"), net=eur("252.04"), settlement=Settlement.CASH, threshold=eur("110")),
    # ZC3N1D/OF-4001: 640 − 500 = 140; fees 0; refundable → CASH; max(25, 32) = 32
    ("ZC3N1D", "OF-4001"): dict(pax=1, gross=usd("140"), fees=usd("0"), net=usd("140"), settlement=Settlement.CASH, threshold=usd("32")),
    # HB6W9E/OF-5001: 260 − 200 = 60; fees 150; net −90; max(25, 13) = 25
    ("HB6W9E", "OF-5001"): dict(pax=1, gross=usd("60"), fees=usd("150"), net=usd("-90"), settlement=Settlement.CREDIT, threshold=usd("25")),
    # HB6W9E/OF-5002: 260 − 150 = 110; fees = the TICKET's 150, not the offer's 0 (D-18) → net −40 (not +110)
    ("HB6W9E", "OF-5002"): dict(pax=1, gross=usd("110"), fees=usd("150"), net=usd("-40"), settlement=Settlement.CREDIT, threshold=usd("25")),
}


@pytest.mark.parametrize("locator, offer_id", list(FIXTURE_BREAKDOWNS), ids=[f"{p}-{o}" for p, o in FIXTURE_BREAKDOWNS])
def test_fixture_breakdowns(locator, offer_id):
    expected = FIXTURE_BREAKDOWNS[(locator, offer_id)]
    pnr, offer_ = fixture_pnr(locator), fixture_offer(offer_id)
    bd = compute_saving(pnr, offer_, fx=FX, as_of=AS_OF)
    assert bd.passengers == expected["pax"]
    assert bd.paid_per_passenger == pnr.ticket.price_per_passenger
    assert bd.offer_price_per_passenger == offer_.price
    assert bd.gross_saving == expected["gross"]
    assert bd.change_fees == expected["fees"]
    assert bd.net_saving == expected["net"]
    assert bd.settlement is expected["settlement"]
    assert bd.counted_net_saving == expected["net"]  # cash_only default: counted = net (D-10)
    assert bd.threshold == expected["threshold"]


def test_same_currency_needs_no_fx_quote():
    bd = compute_saving(fixture_pnr("QX7T2A"), fixture_offer("OF-1001"), fx=FX, as_of=AS_OF)
    assert bd.fx is None
    assert bd.offer_price_per_passenger_in_ticket_currency == usd("300.00")


def test_passengers_multiply_both_the_difference_and_the_fee():
    # LM9P4C: per-pax difference 30 and fee 75 must both be × 2 (framing trap 2: forgetting it gives −15).
    bd = compute_saving(fixture_pnr("LM9P4C"), fixture_offer("OF-2001"), fx=FX, as_of=AS_OF)
    assert (bd.gross_saving, bd.change_fees, bd.net_saving) == (usd("60"), usd("150"), usd("-90"))


def test_fee_is_the_existing_tickets_fee_not_the_offers():
    # D-18: fee basis = existing ticket's changeFeePerPassenger × pax; the offer's fee only matters for a later change.
    pnr = fixture_pnr("HB6W9E")
    base = compute_saving(pnr, fixture_offer("OF-5002"), fx=FX, as_of=AS_OF)
    pricier_offer_fee = compute_saving(pnr, offer_model(offer("OF-5002", fee="400.00")), fx=FX, as_of=AS_OF)
    assert base.change_fees == usd("150")
    assert pricier_offer_fee == base
    higher_ticket_fee = compute_saving(pnr_model(booking("HB6W9E", fee="160.00")), fixture_offer("OF-5002"), fx=FX, as_of=AS_OF)
    assert higher_ticket_fee.change_fees == usd("160")
    assert higher_ticket_fee.net_saving == usd("-50")  # 110 − 160


def test_offer_is_converted_into_the_ticket_currency():
    # D-27: offers are converted into the ticket's currency; every amount except the quoted offer price is in EUR.
    bd = compute_saving(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), fx=FX, as_of=AS_OF)
    assert bd.offer_price_per_passenger == usd("2100.00")
    assert bd.offer_price_per_passenger_in_ticket_currency == eur("1947.96")  # 2100 × 0.9276
    assert bd.fx is not None
    assert (bd.fx.from_currency, bd.fx.to_currency, bd.fx.rate) == ("USD", "EUR", MOCK_USD_EUR)
    assert bd.fx.source == "mock-fx-v1"
    assert bd.fx.as_of == AS_OF
    assert bd.change_fees == eur("0")  # the two zero fees are in different currencies and are never mixed


class RecordingFx:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def quote(self, from_currency, to_currency, as_of):
        self.calls.append((from_currency, to_currency, as_of))
        return FxQuote(from_currency=from_currency, to_currency=to_currency, rate=Decimal("0.9"), as_of=as_of, source="recording")


def test_fx_is_requested_offer_to_ticket_currency_at_the_injected_as_of():
    fx = RecordingFx()
    later = AS_OF + timedelta(hours=5)
    bd = compute_saving(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), fx=fx, as_of=later)
    assert ("USD", "EUR", later) in fx.calls
    assert all(call[2] == later for call in fx.calls)
    assert bd.offer_price_per_passenger_in_ticket_currency == eur("1890.0")  # 2100 × 0.9
    assert bd.fx.source == "recording"


def test_fx_conversion_is_not_rounded():
    # 2100 × 0.92761 = 1947.981 EUR → gross 252.019 EUR, exactly (rounding is presentation-only).
    fx = MockFxProvider(rates={("USD", "EUR"): Decimal("0.92761")})
    bd = compute_saving(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), fx=fx, as_of=AS_OF)
    assert bd.offer_price_per_passenger_in_ticket_currency.amount == Decimal("1947.981")
    assert bd.gross_saving.amount == Decimal("252.019")


def test_missing_fx_pair_raises_from_compute_saving():
    with pytest.raises(FxUnavailableError):
        compute_saving(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), fx=NO_FX, as_of=AS_OF)


@pytest.mark.parametrize(
    "settlement_policy, factor, expected_counted",
    [
        (SettlementPolicy.CASH_ONLY, Decimal("0.70"), usd("80")),  # counted = net
        (SettlementPolicy.CREDIT_FACE_VALUE, Decimal("0.70"), usd("80")),  # counted = net
        (SettlementPolicy.CREDIT_DISCOUNTED, Decimal("0.70"), usd("26")),  # 180 × 0.70 − 100 = 26
        (SettlementPolicy.CREDIT_DISCOUNTED, Decimal("0.65"), usd("17")),  # 180 × 0.65 − 100 = 17
        (SettlementPolicy.CREDIT_DISCOUNTED, Decimal("0.50"), usd("-10")),  # 180 × 0.50 − 100 = −10
    ],
)
def test_counted_net_for_a_credit_settlement(settlement_policy, factor, expected_counted):
    # D-10: QX7T2A is non-refundable → CREDIT. Only credit_discounted changes the counted amount; net stays 80.
    policy = PolicyConfig(settlement_policy=settlement_policy, credit_discount_factor=factor)
    bd = compute_saving(fixture_pnr("QX7T2A"), fixture_offer("OF-1001"), fx=FX, as_of=AS_OF, policy=policy)
    assert bd.settlement is Settlement.CREDIT
    assert bd.net_saving == usd("80")
    assert bd.counted_net_saving == expected_counted


def test_credit_discount_applies_to_gross_before_fees_with_passengers():
    # LM9P4C: 60 × 0.70 − 150 = −108 (the discount applies to the gross difference, the fee is paid in full).
    policy = PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED)
    bd = compute_saving(fixture_pnr("LM9P4C"), fixture_offer("OF-2001"), fx=FX, as_of=AS_OF, policy=policy)
    assert bd.counted_net_saving == usd("-108")


@pytest.mark.parametrize("settlement_policy", list(SettlementPolicy))
def test_cash_settlement_is_counted_at_face_value_under_every_policy(settlement_policy):
    bd = compute_saving(fixture_pnr("ZC3N1D"), fixture_offer("OF-4001"), fx=FX, as_of=AS_OF, policy=PolicyConfig(settlement_policy=settlement_policy))
    assert bd.settlement is Settlement.CASH
    assert bd.counted_net_saving == bd.net_saving == usd("140")


@pytest.mark.parametrize(
    "policy, locator, offer_id, expected",
    [
        (PolicyConfig(), "QX7T2A", "OF-1001", usd("25")),  # max(25, 24)
        (PolicyConfig(), "ZC3N1D", "OF-4001", usd("32")),  # max(25, 32)
        (PolicyConfig(), "LM9P4C", "OF-2001", usd("35")),  # 5% of totalPaid 700, not of 350 per pax
        (PolicyConfig(min_net_absolute=Decimal("50")), "QX7T2A", "OF-1001", usd("50")),  # max(50, 24)
        (PolicyConfig(min_net_fraction=Decimal("0.10")), "ZC3N1D", "OF-4001", usd("64")),  # max(25, 64)
        (PolicyConfig(min_net_absolute=Decimal("0"), min_net_fraction=Decimal("0")), "QX7T2A", "OF-1001", usd("0")),
    ],
)
def test_threshold_is_max_of_absolute_and_fraction_of_total_paid(policy, locator, offer_id, expected):
    bd = compute_saving(fixture_pnr(locator), fixture_offer(offer_id), fx=FX, as_of=AS_OF, policy=policy)
    assert bd.threshold == expected


# --- check_policy / assess: one rule at a time on a clean base ----------------------------------------------------
# Base: QX7T2A (1 pax, ECONOMY, 1 bag, AA118 08:00, non-refundable, fee 100) × OF-1001 (same flight, 300) → CLEAN.
# Different flights get a different flight number, so "same flight" is unambiguous.

RULE_CASES = {
    "clean-base": ({}, Tier.CLEAN, ()),
    "fewer-bags": ({"bags": 0}, Tier.INELIGIBLE, (Reason.FEWER_BAGS,)),  # D-11: the only product hard block
    "more-bags": ({"bags": 2}, Tier.CLEAN, ()),
    "outside-window-late": ({"flight_number": "AA120", "shift_minutes": 61}, Tier.INELIGIBLE, (Reason.SCHEDULE_OUTSIDE_WINDOW,)),  # D-14
    "outside-window-early": ({"flight_number": "AA120", "shift_minutes": -61}, Tier.INELIGIBLE, (Reason.SCHEDULE_OUTSIDE_WINDOW,)),
    "window-edge-late": ({"flight_number": "AA120", "shift_minutes": 60}, Tier.REVIEW_LEVEL, (Reason.DIFFERENT_FLIGHT,)),  # |60| ≤ 60
    "window-edge-early": ({"flight_number": "AA120", "shift_minutes": -60}, Tier.REVIEW_LEVEL, (Reason.DIFFERENT_FLIGHT,)),
    "other-flight-same-time": ({"flight_number": "AA120"}, Tier.REVIEW_LEVEL, (Reason.DIFFERENT_FLIGHT,)),
    "arrives-later-day": ({"later_day": True}, Tier.INELIGIBLE, (Reason.ARRIVES_LATER_DAY,)),  # D-14
    "net-below-threshold": ({"price": "456.00"}, Tier.INELIGIBLE, (Reason.NET_SAVING_BELOW_THRESHOLD,)),  # 24 − 100 = −76 < 25
    "net-equals-threshold": ({"price": "355.00"}, Tier.CLEAN, ()),  # 125 − 100 = 25, not < 25 (D-13)
    "net-just-below-threshold": ({"price": "355.01"}, Tier.INELIGIBLE, (Reason.NET_SAVING_BELOW_THRESHOLD,)),  # 24.99 < 25
    "no-seats": ({"seats": 0}, Tier.INELIGIBLE, (Reason.INSUFFICIENT_SEATS,)),
    "seats-equal-pax": ({"seats": 1}, Tier.CLEAN, ()),
    "cabin-downgrade": ({"cabin": "BASIC_ECONOMY"}, Tier.REVIEW_LEVEL, (Reason.CABIN_DOWNGRADE,)),  # D-11: review-level
    "cabin-upgrade": ({"cabin": "PREMIUM_ECONOMY"}, Tier.CLEAN, ()),  # not a listed difference
    "added-stop": ({"stops": 1}, Tier.REVIEW_LEVEL, (Reason.ADDED_STOP,)),
    "gains-refundability": ({"refundable": True}, Tier.CLEAN, ()),
}


@pytest.mark.parametrize("case", list(RULE_CASES))
def test_single_rule(case):
    edits, tier, reasons = RULE_CASES[case]
    a = assess_records(booking("QX7T2A"), offer("OF-1001", **edits))
    assert a.tier is tier
    assert a.reasons == reasons


def test_refundability_lost_is_review_level():
    # ZC3N1D (refundable) × OF-4001 (non-refundable), D-11.
    a = assess(fixture_pnr("ZC3N1D"), fixture_offer("OF-4001"), fx=FX, as_of=AS_OF)
    assert a.tier is Tier.REVIEW_LEVEL
    assert a.reasons == (Reason.REFUNDABILITY_LOST,)


def test_arrival_after_midnight_on_the_booked_arrival_day_is_not_later_day():
    # ZC3N1D/OF-4001 departs 22:05 and lands 01:40 the next day, exactly like the booked flight (D-11 consequence).
    a = assess(fixture_pnr("ZC3N1D"), fixture_offer("OF-4001"), fx=FX, as_of=AS_OF)
    assert Reason.ARRIVES_LATER_DAY not in a.reasons


def test_carrier_change_is_review_level():
    a = assess_records(booking("QX7T2A"), offer("OF-1001", carrier="B6", flight_number="B6118"))
    assert a.tier is Tier.REVIEW_LEVEL
    assert Reason.CARRIER_CHANGE in a.reasons
    assert not set(a.reasons) & HARD_BLOCKS


def test_seats_are_checked_against_all_passengers():
    # LM9P4C (2 pax, fee 75) × UA642 at 13:30 in ECONOMY with 1 bag for 250: (350 − 250) × 2 − 150 = 50 ≥ 35.
    same_flight = dict(flight_number="UA642", shift_minutes=20, cabin="ECONOMY", bags=1, fare_basis="KUA14", price="250.00")
    one_seat = assess_records(booking("LM9P4C"), offer("OF-2001", seats=1, **same_flight))
    two_seats = assess_records(booking("LM9P4C"), offer("OF-2001", seats=2, **same_flight))
    assert (one_seat.tier, one_seat.reasons) == (Tier.INELIGIBLE, (Reason.INSUFFICIENT_SEATS,))
    assert (two_seats.tier, two_seats.reasons) == (Tier.CLEAN, ())


# Reasons follow the rule order of the policy docstring (hard blocks, then review-level), deduplicated.
FIXTURE_ASSESSMENTS = {
    ("QX7T2A", "OF-1001"): (Tier.CLEAN, (), 0),
    # bags 1→0, net −90 < 35, ECONOMY→BASIC_ECONOMY, UA642→UA640 at −20 min (within ±60)
    ("LM9P4C", "OF-2001"): (Tier.INELIGIBLE, (Reason.FEWER_BAGS, Reason.NET_SAVING_BELOW_THRESHOLD, Reason.CABIN_DOWNGRADE, Reason.DIFFERENT_FLIGHT), -20),
    ("ZC3N1D", "OF-4001"): (Tier.REVIEW_LEVEL, (Reason.REFUNDABILITY_LOST,), 0),
    ("HB6W9E", "OF-5001"): (Tier.INELIGIBLE, (Reason.NET_SAVING_BELOW_THRESHOLD,), 0),  # −90 < 25
    # bags 1→0; 21:20 − 06:45 = +875 min > 60; arrives 08-31 > 08-30; −40 < 25; BASIC_ECONOMY; AS→F9; 0→1 stop.
    # DIFFERENT_FLIGHT is the *within-window* reason, so it is not added outside the window.
    ("HB6W9E", "OF-5002"): (
        Tier.INELIGIBLE,
        (Reason.FEWER_BAGS, Reason.SCHEDULE_OUTSIDE_WINDOW, Reason.ARRIVES_LATER_DAY, Reason.NET_SAVING_BELOW_THRESHOLD,
         Reason.CABIN_DOWNGRADE, Reason.CARRIER_CHANGE, Reason.ADDED_STOP),
        875,
    ),
}


@pytest.mark.parametrize("locator, offer_id", list(FIXTURE_ASSESSMENTS), ids=[f"{p}-{o}" for p, o in FIXTURE_ASSESSMENTS])
def test_fixture_assessments(locator, offer_id):
    tier, reasons, shift = FIXTURE_ASSESSMENTS[(locator, offer_id)]
    offer_ = fixture_offer(offer_id)
    a = assess(fixture_pnr(locator), offer_, fx=FX, as_of=AS_OF)
    assert a.offer_id == offer_id
    assert a.tier is tier
    assert a.reasons == reasons  # review-level reasons are still recorded on ineligible offers
    assert a.schedule_shift_minutes == shift  # signed: offer departure − booked departure
    assert a.seats_available == offer_.seats_available


def test_fx_converted_offer_stays_clean():
    # RT5K8B/OF-3001: FX_CONVERTED is informational and never changes the tier.
    a = assess(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), fx=FX, as_of=AS_OF)
    assert a.tier is Tier.CLEAN
    assert set(a.reasons) <= {Reason.FX_CONVERTED}
    assert a.breakdown is not None and a.breakdown.fx is not None


@pytest.mark.parametrize(
    "edits, expected",
    [
        ({}, (Reason.CURRENCY_MISMATCH_NO_FX,)),
        ({"refundable": False}, (Reason.CURRENCY_MISMATCH_NO_FX, Reason.REFUNDABILITY_LOST)),
        ({"bags": 1}, (Reason.FEWER_BAGS, Reason.CURRENCY_MISMATCH_NO_FX)),
    ],
)
def test_fx_unavailable_is_ineligible_without_a_breakdown(edits, expected):
    # D-27: no rate → CURRENCY_MISMATCH_NO_FX and breakdown None. The saving is unknown, not "below threshold".
    a = assess_records(booking("RT5K8B"), offer("OF-3001", **edits), fx=NO_FX)
    assert a.tier is Tier.INELIGIBLE
    assert a.breakdown is None
    assert a.reasons == expected


def test_check_policy_without_breakdown_is_currency_mismatch():
    a = check_policy(fixture_pnr("RT5K8B"), fixture_offer("OF-3001"), None, as_of=AS_OF)
    assert a.tier is Tier.INELIGIBLE
    assert a.breakdown is None
    assert Reason.CURRENCY_MISMATCH_NO_FX in a.reasons
    assert Reason.NET_SAVING_BELOW_THRESHOLD not in a.reasons


@pytest.mark.parametrize("locator, offer_id", [("QX7T2A", "OF-1001"), ("LM9P4C", "OF-2001"), ("RT5K8B", "OF-3001"), ("HB6W9E", "OF-5002")])
def test_assess_is_compute_saving_then_check_policy(locator, offer_id):
    pnr, offer_ = fixture_pnr(locator), fixture_offer(offer_id)
    bd = compute_saving(pnr, offer_, fx=FX, as_of=AS_OF)
    assert assess(pnr, offer_, fx=FX, as_of=AS_OF) == check_policy(pnr, offer_, bd, as_of=AS_OF)
    assert check_policy(pnr, offer_, bd, as_of=AS_OF).breakdown == bd


def test_policy_schedule_window_is_configurable():
    record = offer("OF-1001", flight_number="AA120", shift_minutes=75)
    assert assess_records(booking("QX7T2A"), record).reasons == (Reason.SCHEDULE_OUTSIDE_WINDOW,)
    wide = PolicyConfig(schedule_window=timedelta(minutes=90))
    assert assess_records(booking("QX7T2A"), record, policy=wide).reasons == (Reason.DIFFERENT_FLIGHT,)


def test_policy_threshold_is_configurable():
    a = assess_records(booking("QX7T2A"), offer("OF-1001"), policy=PolicyConfig(min_net_absolute=Decimal("100")))
    assert (a.tier, a.reasons) == (Tier.INELIGIBLE, (Reason.NET_SAVING_BELOW_THRESHOLD,))  # 80 < 100


def test_threshold_uses_the_counted_net():
    # credit_discounted 0.65: QX7T2A counted 180 × 0.65 − 100 = 17 < 25, although net is 80 (D-10, D-13).
    policy = PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED, credit_discount_factor=Decimal("0.65"))
    a = assess_records(booking("QX7T2A"), offer("OF-1001"), policy=policy)
    assert (a.tier, a.reasons) == (Tier.INELIGIBLE, (Reason.NET_SAVING_BELOW_THRESHOLD,))


# --- rule trace ---------------------------------------------------------------------------------------------------

def _fixture_assessment(locator, offer_id):
    return assess(fixture_pnr(locator), fixture_offer(offer_id), fx=FX, as_of=AS_OF)


@pytest.mark.parametrize("locator, offer_id", list(FIXTURE_ASSESSMENTS), ids=[f"{p}-{o}" for p, o in FIXTURE_ASSESSMENTS])
def test_rule_trace_is_complete_and_explains_the_reasons(locator, offer_id):
    a = _fixture_assessment(locator, offer_id)
    names = [r.rule for r in a.rule_trace]
    assert names, "every assessment carries a rule trace"
    assert len(names) == len(set(names)), "each rule appears once"
    assert all(isinstance(r.detail, str) and r.detail for r in a.rule_trace), "each rule records its value"
    failed = [r for r in a.rule_trace if not r.passed]
    # Each failing rule adds its reason (deduplicated), so reasons exist exactly when some rule failed.
    assert bool(failed) == bool(a.reasons)
    assert len(failed) >= len(a.reasons)


def test_rule_trace_does_not_short_circuit():
    clean = _fixture_assessment("QX7T2A", "OF-1001")
    blocked = _fixture_assessment("HB6W9E", "OF-5002")
    assert all(r.passed for r in clean.rule_trace)
    assert [r.rule for r in blocked.rule_trace] == [r.rule for r in clean.rule_trace]
    assert sum(not r.passed for r in blocked.rule_trace) >= 7


def test_reasons_are_deduplicated():
    for locator, offer_id in FIXTURE_ASSESSMENTS:
        reasons = _fixture_assessment(locator, offer_id).reasons
        assert len(reasons) == len(set(reasons))


# --- property: tiers agree with an independent restatement of the rules -------------------------------------------

@settings(max_examples=150, deadline=None)
@given(booking_records(), offer_records(), policies())
def test_tier_and_reasons_match_the_rules(booking_record, offer_record, policy):
    pnr, offer_ = pnr_model(booking_record), offer_model(offer_record)
    a = assess(pnr, offer_, fx=FX, as_of=AS_OF, policy=policy)
    hard = spec_hard_blocks(pnr, offer_, policy, DEFAULT_RATES)
    review_required, review_allowed = spec_review_reasons(pnr, offer_, policy, DEFAULT_RATES)
    reasons = set(a.reasons)
    assert reasons & HARD_BLOCKS == hard
    assert review_required <= reasons & REVIEW_LEVEL_REASONS <= review_allowed
    assert a.tier is (Tier.INELIGIBLE if hard else Tier.REVIEW_LEVEL if review_required else Tier.CLEAN)
    assert (a.breakdown is None) == (Reason.CURRENCY_MISMATCH_NO_FX in hard)
