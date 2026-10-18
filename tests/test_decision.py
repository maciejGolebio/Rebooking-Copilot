"""Deterministic decision engine, stub mode (decision.py docstring; D-10, D-11, D-13–D-15, D-18, D-24, D-26–D-29).

Every expected value below was derived from the docstring formulas with a script, not by hand; the formula is in a
comment next to each case. Edge cases are built from deep copies of the fixture JSON (tests/factories.py).
"""

import copy
import re
from collections import Counter
from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from factories import (
    CAPTURED_AT, MOCK_USD_EUR, assert_breakdown_recomputable, booking, eur, fixture_inputs, fixture_pnr, load, offer,
    offer_model, pnr_model, raw, raw_booking, raw_offer, scenarios, spec_hard_blocks, usd,
)
from rebooking_copilot.decision import REASONER_ID, Action, Confidence, Recommendation, evaluate
from rebooking_copilot.fx import MockFxProvider
from rebooking_copilot.loader import parse_fare_snapshot, parse_pnrs
from rebooking_copilot.policy import HARD_BLOCKS, REVIEW_LEVEL_REASONS, PolicyConfig, Reason, Settlement, SettlementPolicy, Tier

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_RATES = {("USD", "EUR"): MOCK_USD_EUR}
NON_MONEY_BLOCKS = {Reason.FEWER_BAGS, Reason.SCHEDULE_OUTSIDE_WINDOW, Reason.ARRIVES_LATER_DAY, Reason.INSUFFICIENT_SEATS}
LOCATORS = ["QX7T2A", "LM9P4C", "RT5K8B", "ZC3N1D", "HB6W9E"]


def run(bookings: list[dict], offers: list[dict], **kwargs) -> tuple[Recommendation, ...]:
    pnr_load, snapshot = load(bookings, offers)
    return evaluate(pnr_load, snapshot, **kwargs)


def fixture_run(**kwargs) -> tuple[Recommendation, ...]:
    return evaluate(*fixture_inputs(), **kwargs)


def by_pnr(recs) -> dict[str | None, Recommendation]:
    return {r.pnr: r for r in recs}


def candidate(rec: Recommendation, offer_id: str):
    (assessment,) = [a for a in rec.candidates if a.offer_id == offer_id]
    return assessment


def summary(rec: Recommendation) -> tuple:
    return rec.action, rec.chosen_offer_id, rec.estimated_net_saving, rec.confidence, rec.reasons


def assert_seats_never_oversold(recs, offer_records: list[dict]) -> None:
    taken = Counter()
    for r in recs:
        if r.action is Action.REBOOK:
            taken[r.chosen_offer_id] += r.breakdown.passengers
    seats = {o["offerId"]: o["seatsAvailable"] for o in offer_records}
    assert all(taken[oid] <= seats[oid] for oid in taken)


def zc(**edits) -> dict:
    """ZC3N1D: 1 pax, 640 USD, refundable (CASH), fee 0, 1 bag, AV24 22:05 → threshold max(25, 5% × 640) = 32."""
    return booking("ZC3N1D", **edits)


def zc_clean(**edits) -> dict:
    """OF-4001 made refundable: the same flight and product as ZC3N1D → CLEAN; 500 USD → net 140."""
    return offer("OF-4001", refundable=True, **edits)


# =================================================================================================================
# a) Golden: the five fixture bookings, default policy, MockFxProvider(), as_of = capturedAt (2026-07-08T09:00Z)
# gross = (paid pp − offer pp in ticket ccy) × pax; fees = existing ticket fee pp × pax (D-18); net = gross − fees;
# threshold = max(25, 5% × totalPaid) (D-13); settlement CASH iff ticket refundable (D-10); default cash_only.
# =================================================================================================================

GOLDEN = {
    # QX7T2A × OF-1001 (same flight, product, bags): gross (480 − 300) × 1 = 180; fees 100 × 1 = 100; net 80 ≥ max(25, 24) = 25
    # → CLEAN. Non-refundable → CREDIT; cash_only → NEEDS_REVIEW + SAVING_AS_CREDIT (D-10); NEEDS_REVIEW → LOW (D-28).
    # estimated = counted net = net = 80 (counted ≠ net only under credit_discounted).
    "QX7T2A": (Action.NEEDS_REVIEW, "OF-1001", usd("80.00"), Confidence.LOW, (Reason.SAVING_AS_CREDIT,)),
    # LM9P4C × OF-2001: gross (350 − 320) × 2 = 60; fees 75 × 2 = 150; net −90 < max(25, 5% × 700) = 35; bags 1→0 (D-11);
    # ECONOMY→BASIC_ECONOMY; UA642→UA640 at −20 min, within ±60 (D-14) → INELIGIBLE. No eligible offer → DO_NOT_REBOOK with
    # every candidate reason; the only candidate has net ≤ 0 → HIGH (D-28).
    "LM9P4C": (
        Action.DO_NOT_REBOOK, None, None, Confidence.HIGH,
        (Reason.FEWER_BAGS, Reason.NET_SAVING_BELOW_THRESHOLD, Reason.CABIN_DOWNGRADE, Reason.DIFFERENT_FLIGHT),
    ),
    # RT5K8B × OF-3001: 2100 USD × 0.9276 = 1947.96 EUR (D-27); gross (2200 − 1947.96) × 1 = 252.04 EUR; fees 0 × 1; net 252.04
    # ≥ max(25, 5% × 2200) = 110 EUR → CLEAN; refundable → CASH → REBOOK + FX_CONVERTED. Confidence HIGH, −1 for FX → MEDIUM;
    # 252.04 ≥ 2 × 110 = 220 and snapshot age 0 ≤ 1 day → no further drop (D-28).
    "RT5K8B": (Action.REBOOK, "OF-3001", eur("252.04"), Confidence.MEDIUM, (Reason.FX_CONVERTED,)),
    # ZC3N1D × OF-4001: gross (640 − 500) × 1 = 140; fees 0; net 140 ≥ max(25, 32) = 32; refundable → non-refundable =
    # REVIEW_LEVEL (D-11) → stub NEEDS_REVIEW with REFUNDABILITY_LOST (D-18); LOW (D-28).
    "ZC3N1D": (Action.NEEDS_REVIEW, "OF-4001", usd("140.00"), Confidence.LOW, (Reason.REFUNDABILITY_LOST,)),
    # HB6W9E × OF-5001: (260 − 200) × 1 − 150 = −90 < 25 → INELIGIBLE.
    # HB6W9E × OF-5002: (260 − 150) × 1 − 150 (the ticket's fee, D-18) = −40 < 25; bags 1→0; 21:20 − 06:45 = +875 min > 60 and
    # arrives 08-31 > 08-30 (D-14); BASIC_ECONOMY; AS→F9; 0→1 stop → INELIGIBLE (DIFFERENT_FLIGHT is the within-window reason).
    # → DO_NOT_REBOOK, reasons deduplicated in first-seen order over candidates in input order; both nets ≤ 0 → HIGH.
    "HB6W9E": (
        Action.DO_NOT_REBOOK, None, None, Confidence.HIGH,
        (Reason.NET_SAVING_BELOW_THRESHOLD, Reason.FEWER_BAGS, Reason.SCHEDULE_OUTSIDE_WINDOW, Reason.ARRIVES_LATER_DAY,
         Reason.CABIN_DOWNGRADE, Reason.CARRIER_CHANGE, Reason.ADDED_STOP),
    ),
}

GOLDEN_CANDIDATES = {
    "QX7T2A": {"OF-1001": Tier.CLEAN},
    "LM9P4C": {"OF-2001": Tier.INELIGIBLE},
    "RT5K8B": {"OF-3001": Tier.CLEAN},
    "ZC3N1D": {"OF-4001": Tier.REVIEW_LEVEL},
    "HB6W9E": {"OF-5001": Tier.INELIGIBLE, "OF-5002": Tier.INELIGIBLE},
}


@pytest.mark.parametrize("locator", list(GOLDEN))
def test_golden(locator):
    action, offer_id, net, confidence, reasons = GOLDEN[locator]
    rec = by_pnr(fixture_run())[locator]
    assert rec.action is action
    assert rec.chosen_offer_id == offer_id
    if net is None:
        assert rec.estimated_net_saving is None
    else:
        assert rec.estimated_net_saving.currency == net.currency
        assert isinstance(rec.estimated_net_saving.amount, Decimal)
        assert rec.estimated_net_saving.amount == net.amount  # exact, no rounding
    assert rec.confidence is confidence
    assert rec.reasons == reasons


@pytest.mark.parametrize("locator", list(GOLDEN_CANDIDATES))
def test_golden_candidates_and_tiers(locator):
    rec = by_pnr(fixture_run())[locator]
    assert {a.offer_id: a.tier for a in rec.candidates} == GOLDEN_CANDIDATES[locator]
    assert tuple(a.offer_id for a in rec.candidates) == tuple(GOLDEN_CANDIDATES[locator])  # input order
    assert rec.alternatives == ()  # no booking in the fixtures has a second eligible offer


def test_golden_breakdown_of_the_chosen_offer():
    recs = by_pnr(fixture_run())
    for locator, (_, offer_id, net, _, _) in GOLDEN.items():
        rec = recs[locator]
        if offer_id is None:
            assert rec.breakdown is None
            continue
        assert rec.breakdown == candidate(rec, offer_id).breakdown
        assert rec.breakdown.counted_net_saving == net
        assert_breakdown_recomputable(rec.breakdown, fixture_pnr(locator), PolicyConfig())
    rt = recs["RT5K8B"].breakdown
    assert rt.settlement is Settlement.CASH
    assert rt.fx is not None and rt.fx.rate == MOCK_USD_EUR and rt.fx.source == "mock-fx-v1" and rt.fx.as_of == CAPTURED_AT
    assert rt.offer_price_per_passenger_in_ticket_currency == eur("1947.96")
    assert recs["QX7T2A"].breakdown.settlement is Settlement.CREDIT


def test_golden_metadata():
    recs = fixture_run()
    assert [r.index for r in recs] == [0, 1, 2, 3, 4]
    assert [r.pnr for r in recs] == LOCATORS
    for r in recs:
        assert r.reasoner == REASONER_ID == "stub"
        assert r.policy_version == "v1"
        assert r.as_of == CAPTURED_AT  # D-18: as_of defaults to capturedAt
        assert r.expires_at == CAPTURED_AT + timedelta(days=1)  # D-24: as_of + one reshop interval
        assert r.data_issues == ()
        assert SHA256_HEX.match(r.fingerprint)


def test_default_fx_is_the_mock_provider():
    assert fixture_run() == fixture_run(fx=MockFxProvider())


# =================================================================================================================
# b) Invariants (money-safety skill) that hold without a reasoner
# =================================================================================================================

@pytest.mark.parametrize(
    "policy",
    [
        PolicyConfig(),
        PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_FACE_VALUE),
        PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED),
    ],
    ids=["cash_only", "credit_face_value", "credit_discounted"],
)
def test_every_number_is_recomputable_from_the_output(policy):
    # Invariant 1: estimated_net_saving == breakdown.counted_net_saving, and every breakdown field follows from the inputs.
    for rec in fixture_run(policy=policy):
        pnr = fixture_pnr(rec.pnr)
        if rec.breakdown is not None:
            assert rec.estimated_net_saving == rec.breakdown.counted_net_saving
        for a in rec.candidates:
            if a.breakdown is not None:
                assert_breakdown_recomputable(a.breakdown, pnr, policy)


@settings(max_examples=150, deadline=None)
@given(scenarios())
def test_decision_rules_hold_for_generated_bookings(scenario):
    # Invariants 1–3 plus the action rules of the decision.py docstring, checked against an independent restatement
    # of the hard constraints (spec_hard_blocks), for one booking with 1–3 generated offers.
    booking_record, offer_records, policy = scenario
    (rec,) = run([booking_record], offer_records, policy=policy)
    pnr = pnr_model(booking_record)
    offers = {o["offerId"]: offer_model(o) for o in offer_records}
    hard = {oid: spec_hard_blocks(pnr, o, policy, DEFAULT_RATES) for oid, o in offers.items()}
    assessments = {a.offer_id: a for a in rec.candidates}
    assert set(assessments) == set(offers)
    eligible = {oid for oid, a in assessments.items() if a.tier is not Tier.INELIGIBLE}
    clean = {oid for oid, a in assessments.items() if a.tier is Tier.CLEAN}

    # Invariant 3: a failing hard constraint makes the offer ineligible, and never REBOOK.
    for oid, blocks in hard.items():
        if blocks:
            assert assessments[oid].tier is Tier.INELIGIBLE
    if all(hard.values()):
        assert rec.action is not Action.REBOOK

    # Invariant 2: REBOOK ⇒ a CLEAN offer that passes every hard constraint.
    if rec.action is Action.REBOOK:
        chosen, offer_ = assessments[rec.chosen_offer_id], offers[rec.chosen_offer_id]
        assert chosen.tier is Tier.CLEAN
        assert not hard[rec.chosen_offer_id]
        assert not set(chosen.reasons) & (HARD_BLOCKS | REVIEW_LEVEL_REASONS)
        assert offer_.seats_available >= pnr.passengers
        assert chosen.breakdown.counted_net_saving >= chosen.breakdown.threshold
        assert offer_.price.currency == pnr.ticket.price_per_passenger.currency or chosen.breakdown.fx is not None

    # Choice and action rules (D-29, D-15, D-10, D-18).
    if eligible:
        assert rec.chosen_offer_id in eligible
        chosen = assessments[rec.chosen_offer_id]
        if clean:
            assert chosen.tier is Tier.CLEAN  # clean first
            best = max(assessments[oid].breakdown.counted_net_saving for oid in clean)
            assert chosen.breakdown.counted_net_saving == best
            credit_not_counted = chosen.breakdown.settlement is Settlement.CREDIT and policy.settlement_policy is SettlementPolicy.CASH_ONLY
            assert rec.action is (Action.NEEDS_REVIEW if credit_not_counted else Action.REBOOK)
        else:
            assert rec.action is Action.NEEDS_REVIEW  # the stub never approves a review-level offer
        assert set(rec.alternatives) == eligible - {rec.chosen_offer_id}
    else:
        assert rec.chosen_offer_id is None and rec.alternatives == ()
        any_no_fx = any(Reason.CURRENCY_MISMATCH_NO_FX in a.reasons for a in rec.candidates)
        assert rec.action is (Action.NEEDS_REVIEW if any_no_fx else Action.DO_NOT_REBOOK)

    # Invariant 1: the reported saving is the chosen offer's, recomputable from the breakdown.
    if rec.chosen_offer_id is None:
        assert rec.estimated_net_saving is None and rec.breakdown is None
    else:
        assert rec.breakdown == assessments[rec.chosen_offer_id].breakdown
        assert rec.estimated_net_saving == rec.breakdown.counted_net_saving
    for a in rec.candidates:
        if a.breakdown is not None:
            assert_breakdown_recomputable(a.breakdown, pnr, policy)

    # Confidence (D-28), as_of = capturedAt so the snapshot is never stale here.
    if rec.action is Action.NEEDS_REVIEW:
        assert rec.confidence is Confidence.LOW
    elif rec.action is Action.REBOOK:
        bd = rec.breakdown
        unpriced = any(Reason.CURRENCY_MISMATCH_NO_FX in a.reasons for a in rec.candidates)  # D-41
        drops = (bd.fx is not None) + (bd.counted_net_saving.amount < policy.confidence_margin_multiple * bd.threshold.amount) + unpriced
        assert rec.confidence is (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW)[min(drops, 2)]
    else:
        settled = all(a.breakdown.net_saving.amount <= 0 or set(a.reasons) & NON_MONEY_BLOCKS for a in rec.candidates)
        assert rec.confidence is (Confidence.HIGH if settled else Confidence.MEDIUM)


def _assert_not_toward_rebook(before: Recommendation, after: Recommendation) -> None:
    # Invariant 4: neither DO_NOT_REBOOK nor NEEDS_REVIEW may become REBOOK, and the reported saving never grows.
    if after.action is Action.REBOOK:
        assert before.action is Action.REBOOK
        assert after.estimated_net_saving <= before.estimated_net_saving


@settings(max_examples=100, deadline=None)
@given(scenarios(), st.data())
def test_raising_an_offer_price_never_moves_toward_rebook(scenario, data):
    booking_record, offer_records, policy = scenario
    i = data.draw(st.integers(0, len(offer_records) - 1), label="offer index")
    bump = data.draw(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("500"), places=2), label="price increase")
    raised = copy.deepcopy(offer_records)
    raised[i]["price"]["amount"] += bump
    (before,) = run([booking_record], offer_records, policy=policy)
    (after,) = run([booking_record], raised, policy=policy)
    oid = offer_records[i]["offerId"]
    # D-34: the price-anomaly guard is the deliberate exception: a price rising out of the "too good to be true" band
    # can make the offer eligible, so the invariant is asserted only for offers that started outside that band.
    assume(Reason.PRICE_ANOMALY not in candidate(before, oid).reasons)
    _assert_not_toward_rebook(before, after)
    b0, b1 = candidate(before, oid).breakdown, candidate(after, oid).breakdown
    if b0 is not None and b1 is not None:
        assert b1.net_saving < b0.net_saving
        assert b1.counted_net_saving < b0.counted_net_saving


@settings(max_examples=100, deadline=None)
@given(scenarios(), st.decimals(min_value=Decimal("0.01"), max_value=Decimal("300"), places=2))
def test_raising_the_ticket_fee_never_moves_toward_rebook(scenario, bump):
    booking_record, offer_records, policy = scenario
    higher_fee = copy.deepcopy(booking_record)
    higher_fee["ticket"]["changeFeePerPassenger"]["amount"] += bump
    (before,) = run([booking_record], offer_records, policy=policy)
    (after,) = run([higher_fee], offer_records, policy=policy)
    _assert_not_toward_rebook(before, after)
    for a0 in before.candidates:
        a1 = candidate(after, a0.offer_id)
        if a0.breakdown is not None:
            assert a1.breakdown.net_saving < a0.breakdown.net_saving


@settings(max_examples=50, deadline=None)
@given(scenarios(), st.decimals(min_value=Decimal("0.01"), max_value=Decimal("300"), places=2))
def test_the_offers_own_change_fee_does_not_affect_the_decision(scenario, bump):
    # D-18: the offer's fee only matters for a later change, so raising it changes nothing in today's decision.
    booking_record, offer_records, policy = scenario
    raised = copy.deepcopy(offer_records)
    for o in raised:
        o["changeFeePerPassenger"]["amount"] += bump
    (before,) = run([booking_record], offer_records, policy=policy)
    (after,) = run([booking_record], raised, policy=policy)
    assert summary(after) == summary(before)


def test_same_inputs_give_identical_recommendations_and_fingerprints():
    # Invariant 5 / D-23: stub mode is deterministic, including the serialised output.
    first, second = fixture_run(), fixture_run()
    assert first == second
    assert [r.model_dump_json() for r in first] == [r.model_dump_json() for r in second]
    assert [r.fingerprint for r in first] == [r.fingerprint for r in second]


def test_contention_run_is_deterministic():
    bookings = [zc(pnr="ZC7Q4B", price="600.00"), zc()]
    offers = [zc_clean(seats=1), zc_clean(offer_id="OF-4002", price="560.00", seats=5)]
    assert run(bookings, offers) == run(copy.deepcopy(bookings), copy.deepcopy(offers))


@pytest.mark.parametrize(
    "policy",
    [PolicyConfig(min_net_absolute=Decimal("30")), PolicyConfig(version="v2"), PolicyConfig(reshop_interval=timedelta(hours=6))],
    ids=["threshold", "version", "reshop-interval"],
)
def test_a_different_policy_changes_every_fingerprint(policy):
    base, other = fixture_run(), fixture_run(policy=policy)
    assert all(a.fingerprint != b.fingerprint for a, b in zip(base, other, strict=True))


def test_a_different_as_of_changes_every_fingerprint():
    base, later = fixture_run(), fixture_run(as_of=CAPTURED_AT + timedelta(hours=1))
    assert all(a.fingerprint != b.fingerprint for a, b in zip(base, later, strict=True))


def test_fingerprint_covers_the_bookings_candidate_offers_only():
    data = raw("fares_feed.json")
    data["offers"][0]["price"]["amount"] = Decimal("301.00")  # OF-1001, QX7T2A's only candidate
    base = fixture_run()
    changed = evaluate(fixture_inputs()[0], parse_fare_snapshot(data))
    assert changed[0].fingerprint != base[0].fingerprint
    assert [r.fingerprint for r in changed[1:]] == [r.fingerprint for r in base[1:]]


def test_fingerprint_covers_the_fx_quotes_used():
    base = by_pnr(fixture_run())
    other = by_pnr(fixture_run(fx=MockFxProvider(rates={("USD", "EUR"): Decimal("0.95")})))
    assert other["RT5K8B"].fingerprint != base["RT5K8B"].fingerprint
    for locator in ["QX7T2A", "LM9P4C", "ZC3N1D", "HB6W9E"]:  # no FX used → unchanged
        assert other[locator].fingerprint == base[locator].fingerprint


def test_fingerprint_does_not_depend_on_unrelated_bookings():
    pnrs = raw("pnrs.json")
    pnrs["pnrs"] = pnrs["pnrs"][:4]  # drop HB6W9E, which shares no offer with the others
    without_last = evaluate(parse_pnrs(pnrs), fixture_inputs()[1])
    assert [r.fingerprint for r in without_last] == [r.fingerprint for r in fixture_run()[:4]]


def _mutated_pnrs(mutate) -> dict:
    data = raw("pnrs.json")
    mutate(data["pnrs"])
    return data


def _inconsistent_total(pnrs):
    pnrs[1]["ticket"]["totalPaid"]["amount"] = Decimal("650.00")  # LM9P4C: 650 ≠ 350 × 2


def _missing_locator(pnrs):
    del pnrs[3]["pnr"]  # ZC3N1D without a locator


def _two_segments(pnrs):
    pnrs[0]["itinerary"].append(copy.deepcopy(pnrs[0]["itinerary"][0]))


@pytest.mark.parametrize(
    "mutate, index, locator, code",
    [
        (_inconsistent_total, 1, "LM9P4C", Reason.DATA_INCONSISTENT),
        (_missing_locator, 3, None, Reason.DATA_INVALID),
        (_two_segments, 0, "QX7T2A", Reason.UNSUPPORTED_ITINERARY),
    ],
    ids=["inconsistent-total", "missing-locator", "multi-segment"],
)
def test_rejected_bookings_get_needs_review_with_their_data_codes(mutate, index, locator, code):
    # Invariant 7 / D-00c / D-26: one recommendation per input booking, rejected ones included, in input order.
    pnr_load = parse_pnrs(_mutated_pnrs(mutate))
    (rejected,) = pnr_load.rejected
    recs = evaluate(pnr_load, fixture_inputs()[1])
    assert [r.index for r in recs] == [0, 1, 2, 3, 4]
    rec = recs[index]
    assert rec.pnr == locator
    assert rec.action is Action.NEEDS_REVIEW
    assert rec.reasons == (code,)
    assert rec.confidence is Confidence.LOW
    assert rec.data_issues == rejected.issues
    assert (rec.chosen_offer_id, rec.estimated_net_saving, rec.breakdown) == (None, None, None)
    assert rec.candidates == () and rec.alternatives == ()
    assert rec.as_of == CAPTURED_AT and rec.expires_at == CAPTURED_AT + timedelta(days=1)
    assert SHA256_HEX.match(rec.fingerprint)
    golden = fixture_run()
    for i, other in enumerate(recs):
        if i != index:
            assert summary(other) == summary(golden[i])


def test_output_is_ordered_by_input_index_with_rejections_interleaved():
    def mutate(pnrs):
        _inconsistent_total(pnrs)
        _missing_locator(pnrs)

    recs = evaluate(parse_pnrs(_mutated_pnrs(mutate)), fixture_inputs()[1])
    assert [r.index for r in recs] == [0, 1, 2, 3, 4]
    assert [r.pnr for r in recs] == ["QX7T2A", "LM9P4C", "RT5K8B", None, "HB6W9E"]
    assert recs[1].action is Action.NEEDS_REVIEW and recs[3].action is Action.NEEDS_REVIEW


def test_every_booking_gets_a_recommendation_even_without_offers():
    pnr_load, _ = fixture_inputs()
    recs = evaluate(pnr_load, parse_fare_snapshot({"capturedAt": "2026-07-08T09:00:00Z", "offers": []}))
    assert [r.pnr for r in recs] == LOCATORS
    assert all(summary(r) == (Action.DO_NOT_REBOOK, None, None, Confidence.HIGH, (Reason.NO_CANDIDATES,)) for r in recs)


# =================================================================================================================
# c) Edge cases (small inline data, D-18)
# =================================================================================================================

# --- several eligible offers for one booking: clean first (D-29), then D-15 within the tier --------------------------
# Booking ZC3N1D: threshold 32, confidence margin 2 × 32 = 64. Clean variants are refundable copies of OF-4001.

def test_clean_offer_beats_a_bigger_review_level_saving():
    # OF-4001 review-level (refundability lost): 640 − 500 = 140. OF-4002 clean: 640 − 560 = 80 ≥ 32 → REBOOK OF-4002 (D-29);
    # 80 ≥ 64 → HIGH. OF-4001 stays an alternative.
    (rec,) = run([zc()], [offer("OF-4001"), zc_clean(offer_id="OF-4002", price="560.00")])
    assert summary(rec) == (Action.REBOOK, "OF-4002", usd("80.00"), Confidence.HIGH, ())
    assert rec.alternatives == ("OF-4001",)


def test_alternatives_are_the_other_eligible_offers_best_first():
    # Ranking = clean tier by D-15, then review tier: OF-4003 (clean, 100) > OF-4002 (clean, 80) > OF-4001 (review, 140).
    # OF-4004 (0 bags → FEWER_BAGS) is ineligible and never an alternative.
    offers = [
        offer("OF-4001"),
        zc_clean(offer_id="OF-4002", price="560.00"),
        zc_clean(offer_id="OF-4003", price="540.00"),
        zc_clean(offer_id="OF-4004", price="450.00", bags=0),
    ]
    (rec,) = run([zc()], offers)
    assert summary(rec) == (Action.REBOOK, "OF-4003", usd("100.00"), Confidence.HIGH, ())
    assert rec.alternatives == ("OF-4002", "OF-4001")


def test_tie_break_highest_counted_net_first():
    # 640 − 560 = 80 vs 640 − 540 = 100 → OF-4012, although it comes second in the input.
    (rec,) = run([zc()], [zc_clean(offer_id="OF-4011", price="560.00"), zc_clean(offer_id="OF-4012", price="540.00")])
    assert (rec.chosen_offer_id, rec.estimated_net_saving, rec.alternatives) == ("OF-4012", usd("100.00"), ("OF-4011",))


def test_tie_break_smallest_absolute_schedule_shift():
    # Two other flights, both review-level DIFFERENT_FLIGHT, both net 80: |+30| < |−40| → OF-4102, despite the larger id.
    # (Within the clean tier the shift is always 0, so this tie-breaker only matters among review-level offers.)
    offers = [
        zc_clean(offer_id="OF-4101", flight_number="AV22", shift_minutes=-40, price="560.00"),
        zc_clean(offer_id="OF-4102", flight_number="AV26", shift_minutes=30, price="560.00"),
    ]
    (rec,) = run([zc()], offers)
    assert summary(rec) == (Action.NEEDS_REVIEW, "OF-4102", usd("80.00"), Confidence.LOW, (Reason.DIFFERENT_FLIGHT,))
    assert rec.alternatives == ("OF-4101",)


def test_tie_break_most_seats_in_the_clean_tier():
    # Same flight, both net 80, shift 0: 6 seats beat 2.
    (rec,) = run([zc()], [zc_clean(offer_id="OF-4201", price="560.00", seats=2), zc_clean(offer_id="OF-4202", price="560.00", seats=6)])
    assert (rec.action, rec.chosen_offer_id, rec.alternatives) == (Action.REBOOK, "OF-4202", ("OF-4201",))


def test_tie_break_most_seats_after_equal_absolute_shift():
    # −30 and +30 are the same |shift|, so seats decide: 8 > 3 → OF-4302 (a signed comparison would wrongly pick −30).
    offers = [
        zc_clean(offer_id="OF-4301", flight_number="AV22", shift_minutes=-30, price="560.00", seats=3),
        zc_clean(offer_id="OF-4302", flight_number="AV26", shift_minutes=30, price="560.00", seats=8),
    ]
    (rec,) = run([zc()], offers)
    assert (rec.action, rec.chosen_offer_id, rec.alternatives) == (Action.NEEDS_REVIEW, "OF-4302", ("OF-4301",))


def test_tie_break_offer_id_last():
    # Everything equal → offer id ascending (D-29), whatever the input order.
    (rec,) = run([zc()], [zc_clean(offer_id="OF-4209", price="560.00"), zc_clean(offer_id="OF-4203", price="560.00")])
    assert (rec.chosen_offer_id, rec.alternatives) == ("OF-4203", ("OF-4209",))


# --- seat ledger (D-24) ---------------------------------------------------------------------------------------------

def test_seat_contention_goes_to_the_bigger_counted_saving():
    # One seat on the refundable OF-4001. ZC7Q4B (input 0): 600 − 500 = 100; ZC3N1D (input 1): 640 − 500 = 140.
    # Greedy by counted net → ZC3N1D wins (REBOOK, 140 ≥ 64 → HIGH). ZC7Q4B gets SEAT_CONTENTION, has no other offer →
    # DO_NOT_REBOOK; its candidate had a positive net and failed only on contention → MEDIUM (D-28).
    bookings, offers = [zc(pnr="ZC7Q4B", price="600.00"), zc()], [zc_clean(seats=1)]
    loser, winner = run(bookings, offers)
    assert [loser.index, winner.index] == [0, 1]
    assert summary(winner) == (Action.REBOOK, "OF-4001", usd("140.00"), Confidence.HIGH, ())
    assert summary(loser) == (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.SEAT_CONTENTION,))
    contended = candidate(loser, "OF-4001")
    assert contended.tier is Tier.INELIGIBLE
    assert Reason.SEAT_CONTENTION in contended.reasons
    assert_seats_never_oversold((loser, winner), offers)
    (alone,) = run([zc(pnr="ZC7Q4B", price="600.00")], offers)  # without the competitor it would be a REBOOK
    assert (alone.action, alone.chosen_offer_id) == (Action.REBOOK, "OF-4001")


def test_seat_contention_loser_falls_through_to_its_next_eligible_offer():
    # Add OF-4002 (refundable, 560, 5 seats). ZC3N1D still takes OF-4001 (140) and lists OF-4002 as an alternative.
    # ZC7Q4B: OF-4001 contended → OF-4002: 600 − 560 = 40 ≥ max(25, 30) = 30 → REBOOK; 40 < 2 × 30 = 60 → MEDIUM.
    bookings = [zc(pnr="ZC7Q4B", price="600.00"), zc()]
    offers = [zc_clean(seats=1), zc_clean(offer_id="OF-4002", price="560.00", seats=5)]
    fell_through, winner = run(bookings, offers)
    assert summary(winner) == (Action.REBOOK, "OF-4001", usd("140.00"), Confidence.HIGH, ())
    assert winner.alternatives == ("OF-4002",)
    assert summary(fell_through) == (Action.REBOOK, "OF-4002", usd("40.00"), Confidence.MEDIUM, ())
    assert fell_through.alternatives == ()  # the contended offer is no longer eligible for this booking
    assert Reason.SEAT_CONTENTION in candidate(fell_through, "OF-4001").reasons
    assert_seats_never_oversold((fell_through, winner), offers)


def test_seat_contention_tie_goes_to_the_earlier_booking():
    # Both 640 − 500 = 140 → input index decides: ZC7Q4B (index 0) wins.
    first, second = run([zc(pnr="ZC7Q4B"), zc()], [zc_clean(seats=1)])
    assert (first.action, first.chosen_offer_id) == (Action.REBOOK, "OF-4001")
    assert summary(second) == (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.SEAT_CONTENTION,))


def test_seat_contention_counts_passengers():
    # 3 seats; ZC3N1D ×2 pax: (640 − 500) × 2 = 280 goes first and takes 2; 1 left < 2 pax for ZC7Q4B ((600 − 500) × 2 = 200).
    bookings, offers = [zc(pnr="ZC7Q4B", passengers=2, price="600.00"), zc(passengers=2)], [zc_clean(seats=3)]
    loser, winner = run(bookings, offers)
    assert summary(winner) == (Action.REBOOK, "OF-4001", usd("280.00"), Confidence.HIGH, ())
    assert summary(loser) == (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.SEAT_CONTENTION,))
    assert_seats_never_oversold((loser, winner), offers)


def test_enough_seats_means_no_contention():
    offers = [zc_clean(seats=2)]
    first, second = run([zc(pnr="ZC7Q4B", price="600.00"), zc()], offers)
    assert summary(first) == (Action.REBOOK, "OF-4001", usd("100.00"), Confidence.HIGH, ())
    assert summary(second) == (Action.REBOOK, "OF-4001", usd("140.00"), Confidence.HIGH, ())


def _cross_currency_bookings() -> list[dict]:
    # RT5K8B at 2137.96 EUR: 2137.96 − 2100 × 0.9276 = 190.00 EUR ≥ max(25, 106.898). RT9U1S, a USD ticket at 2300:
    # 2300 − 2100 = 200 USD ≥ 115. Raw amounts (200 > 190) and FX-converted ones (200 × 0.9276 = 185.52 < 190) disagree.
    return [booking("RT5K8B", price="2137.96"), booking("RT5K8B", pnr="RT9U1S", currency="USD", price="2300.00")]


def test_cross_currency_contention_never_oversells():
    # Both bookings want OF-3001 with 1 seat. Whoever wins (see the needs-decision test below), the run must not crash
    # (Money refuses to compare EUR with USD) or sell the seat twice.
    offers = [offer("OF-3001", seats=1)]
    recs = run(_cross_currency_bookings(), offers)
    assert [r.pnr for r in recs] == ["RT5K8B", "RT9U1S"]
    assert_seats_never_oversold(recs, offers)


# --- FX (D-27) ------------------------------------------------------------------------------------------------------

def test_missing_fx_pair_means_needs_review():
    # No USD→EUR rate: RT5K8B's only candidate can't be evaluated → NEEDS_REVIEW CURRENCY_MISMATCH_NO_FX, LOW.
    recs = by_pnr(fixture_run(fx=MockFxProvider(rates={})))
    rt = recs["RT5K8B"]
    assert summary(rt) == (Action.NEEDS_REVIEW, None, None, Confidence.LOW, (Reason.CURRENCY_MISMATCH_NO_FX,))
    assert candidate(rt, "OF-3001").breakdown is None
    golden = by_pnr(fixture_run())
    for locator in ["QX7T2A", "LM9P4C", "ZC3N1D", "HB6W9E"]:  # USD-only bookings are unaffected
        assert summary(recs[locator]) == summary(golden[locator])


def test_missing_fx_beats_do_not_rebook_when_nothing_is_eligible():
    # OF-3002 (EUR, 1 bag < 2) is ineligible on bags; OF-3001 can't be priced → NEEDS_REVIEW, not DO_NOT_REBOOK.
    offers = [raw_offer("OF-3001"), offer("OF-3001", offer_id="OF-3002", currency="EUR", price="2000.00", bags=1)]
    (rec,) = run([raw_booking("RT5K8B")], offers, fx=MockFxProvider(rates={}))
    assert (rec.action, rec.chosen_offer_id, rec.confidence) == (Action.NEEDS_REVIEW, None, Confidence.LOW)
    assert Reason.CURRENCY_MISMATCH_NO_FX in rec.reasons


def test_an_eligible_offer_is_still_chosen_when_another_has_no_fx():
    # OF-3002 in EUR on the same flight: 2200 − 2000 = 200 ≥ 110 → REBOOK without FX; 200 < 220 → MEDIUM; OF-3001
    # couldn't be priced, so the picture is incomplete → one more band down, CANDIDATE_NOT_EVALUATED (D-41).
    offers = [raw_offer("OF-3001"), offer("OF-3001", offer_id="OF-3002", currency="EUR", price="2000.00")]
    (rec,) = run([raw_booking("RT5K8B")], offers, fx=MockFxProvider(rates={}))
    assert summary(rec) == (Action.REBOOK, "OF-3002", eur("200.00"), Confidence.LOW, (Reason.CANDIDATE_NOT_EVALUATED,))


@pytest.mark.parametrize(
    "rate, expected",
    [
        # 2100 × 0.95 = 1995 → 2200 − 1995 = 205 ≥ 110 → REBOOK; −1 FX, −1 for 205 < 220 → LOW.
        ("0.95", (Action.REBOOK, "OF-3001", eur("205"), Confidence.LOW, (Reason.FX_CONVERTED,))),
        # 2100 × 1.00 = 2100 → 100 < 110 → DO_NOT_REBOOK; positive net blocked only by the threshold → MEDIUM.
        ("1.00", (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.NET_SAVING_BELOW_THRESHOLD,))),
    ],
)
def test_rt5k8b_outcome_depends_on_the_rate(rate, expected):
    recs = by_pnr(fixture_run(fx=MockFxProvider(rates={("USD", "EUR"): Decimal(rate)})))
    assert summary(recs["RT5K8B"]) == expected


# --- settlement policy (D-10) on QX7T2A: gross 180, fees 100, net 80, CREDIT, threshold 25, margin 2 × 25 = 50 --------

@pytest.mark.parametrize(
    "policy, expected",
    [
        # cash_only: clean but the 80 would come back as credit → NEEDS_REVIEW, LOW.
        (PolicyConfig(), (Action.NEEDS_REVIEW, "OF-1001", usd("80"), Confidence.LOW, (Reason.SAVING_AS_CREDIT,))),
        # credit_face_value: counted 80 ≥ 25 → REBOOK + SAVING_AS_CREDIT; 80 ≥ 50 → HIGH.
        (PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_FACE_VALUE),
         (Action.REBOOK, "OF-1001", usd("80"), Confidence.HIGH, (Reason.SAVING_AS_CREDIT,))),
        # credit_discounted 0.70: 180 × 0.70 − 100 = 26 ≥ 25 → REBOOK; 26 < 50 → MEDIUM.
        (PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED),
         (Action.REBOOK, "OF-1001", usd("26"), Confidence.MEDIUM, (Reason.SAVING_AS_CREDIT,))),
        # credit_discounted 0.65: 180 × 0.65 − 100 = 17 < 25 → DO_NOT_REBOOK; net 80 > 0, threshold only → MEDIUM.
        (PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED, credit_discount_factor=Decimal("0.65")),
         (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.NET_SAVING_BELOW_THRESHOLD,))),
        # credit_discounted 0.50: counted 180 × 0.50 − 100 = −10, but the rule reads *net* (80 > 0) → still MEDIUM (D-28).
        (PolicyConfig(settlement_policy=SettlementPolicy.CREDIT_DISCOUNTED, credit_discount_factor=Decimal("0.50")),
         (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.NET_SAVING_BELOW_THRESHOLD,))),
    ],
    ids=["cash_only", "credit_face_value", "credit_discounted-0.70", "credit_discounted-0.65", "credit_discounted-0.50"],
)
def test_settlement_policy_changes_qx7t2a(policy, expected):
    assert summary(by_pnr(fixture_run(policy=policy))["QX7T2A"]) == expected


@pytest.mark.parametrize("settlement_policy", list(SettlementPolicy))
def test_settlement_policy_does_not_touch_a_cash_settlement(settlement_policy):
    rec = by_pnr(fixture_run(policy=PolicyConfig(settlement_policy=settlement_policy)))["RT5K8B"]
    assert summary(rec) == GOLDEN["RT5K8B"]


# --- no candidates ------------------------------------------------------------------------------------------------------

def test_no_candidates_is_a_confident_do_not_rebook():
    data = raw("fares_feed.json")
    data["offers"] = [o for o in data["offers"] if o["offerId"] != "OF-1001"]
    rec = by_pnr(evaluate(fixture_inputs()[0], parse_fare_snapshot(data)))["QX7T2A"]
    assert summary(rec) == (Action.DO_NOT_REBOOK, None, None, Confidence.HIGH, (Reason.NO_CANDIDATES,))
    assert rec.candidates == () and rec.alternatives == () and rec.breakdown is None


# --- confidence (D-28) ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "age, expected",
    [
        (timedelta(0), Confidence.HIGH),
        (timedelta(days=1), Confidence.HIGH),  # not *older* than the reshop interval
        (timedelta(days=1, seconds=1), Confidence.MEDIUM),
        (timedelta(days=2), Confidence.MEDIUM),
    ],
)
def test_a_stale_snapshot_lowers_rebook_confidence(age, expected):
    # ZC3N1D × clean OF-4001: net 140 ≥ 64, no FX → HIGH at capturedAt; −1 when as_of − capturedAt > 1 day.
    (rec,) = run([zc()], [zc_clean()], as_of=CAPTURED_AT + age)
    assert (rec.action, rec.confidence) == (Action.REBOOK, expected)


def test_stale_snapshot_and_fx_stack_to_low():
    # RT5K8B: −1 FX, −1 snapshot two days old → LOW. The FX quote is requested at the injected as_of.
    as_of = CAPTURED_AT + timedelta(days=2)
    rec = by_pnr(fixture_run(as_of=as_of))["RT5K8B"]
    assert (rec.action, rec.confidence) == (Action.REBOOK, Confidence.LOW)
    assert rec.breakdown.fx.as_of == as_of


@pytest.mark.parametrize(
    "price, net, expected",
    [("576.00", "64.00", Confidence.HIGH), ("580.00", "60.00", Confidence.MEDIUM)],  # 2 × 32 = 64; "<" lowers, "=" doesn't
)
def test_thin_margin_lowers_rebook_confidence(price, net, expected):
    (rec,) = run([zc()], [zc_clean(price=price)])
    assert summary(rec) == (Action.REBOOK, "OF-4001", usd(net), expected, ())


def test_margin_multiple_is_configurable():
    # 140 < 5 × 32 = 160 → MEDIUM.
    (rec,) = run([zc()], [zc_clean()], policy=PolicyConfig(confidence_margin_multiple=Decimal("5")))
    assert (rec.action, rec.confidence) == (Action.REBOOK, Confidence.MEDIUM)


@pytest.mark.parametrize(
    "offers, reasons, expected",
    [
        # 640 − 620 = 20 > 0 but < 32: a money-only block → MEDIUM.
        ([zc_clean(price="620.00")], (Reason.NET_SAVING_BELOW_THRESHOLD,), Confidence.MEDIUM),
        # net 140 > 0 but 0 seats: a non-money hard block → HIGH.
        ([zc_clean(seats=0)], (Reason.INSUFFICIENT_SEATS,), Confidence.HIGH),
        ([zc_clean(bags=0)], (Reason.FEWER_BAGS,), Confidence.HIGH),
        # one candidate at net −60 (≤ 0), one threshold-only at +20 → not every candidate is settled → MEDIUM.
        ([zc_clean(price="700.00"), zc_clean(offer_id="OF-4002", price="620.00")], (Reason.NET_SAVING_BELOW_THRESHOLD,), Confidence.MEDIUM),
    ],
    ids=["threshold-only", "no-seats", "fewer-bags", "mixed"],
)
def test_do_not_rebook_confidence(offers, reasons, expected):
    (rec,) = run([zc()], offers)
    assert summary(rec) == (Action.DO_NOT_REBOOK, None, None, expected, reasons)


# --- clock and expiry (D-18, D-24) ----------------------------------------------------------------------------------

def test_injected_as_of_and_expiry():
    as_of = CAPTURED_AT + timedelta(hours=3)
    for rec in fixture_run(as_of=as_of):
        assert rec.as_of == as_of
        assert rec.expires_at == as_of + timedelta(days=1)


def test_expiry_follows_the_reshop_interval():
    as_of = CAPTURED_AT + timedelta(hours=3)
    for rec in fixture_run(as_of=as_of, policy=PolicyConfig(reshop_interval=timedelta(hours=6))):
        assert rec.expires_at == as_of + timedelta(hours=6)


# =================================================================================================================
# Seat-ledger and fingerprint rules settled after the test-first pass: D-31 (ledger), D-32 (fingerprint).
# =================================================================================================================

def test_cross_currency_contention_is_ranked_in_the_offer_currency():
    # D-31: rank in the offer's currency (USD) using the inverse of each booking's own FX quote (ranking only).
    # EUR booking: 190.00 EUR / 0.9276 = 204.83 USD > USD booking 200.00 USD → the EUR booking wins.
    # Comparing raw amounts (200 > 190) would pick the USD booking and silently break D-00b.
    eur_booking, usd_booking = run(_cross_currency_bookings(), [offer("OF-3001", seats=1)])
    assert (eur_booking.action, eur_booking.chosen_offer_id) == (Action.REBOOK, "OF-3001")
    assert usd_booking.reasons == (Reason.SEAT_CONTENTION,)


def test_fingerprint_is_per_booking_so_contention_can_change_the_outcome():
    # D-32: the fingerprint covers the booking's own inputs only. ZC3N1D alone → REBOOK OF-4001; with ZC2T7H
    # (700 − 500 = 200 > 140) competing for the 1 seat → SEAT_CONTENTION, under the same fingerprint.
    (alone,) = run([zc()], [zc_clean(seats=1)])
    contended, _ = run([zc(), zc(pnr="ZC2T7H", price="700.00")], [zc_clean(seats=1)])
    assert summary(alone) != summary(contended)
    assert Reason.SEAT_CONTENTION in contended.reasons
    assert alone.fingerprint == contended.fingerprint


def test_rebook_bound_bookings_are_served_before_review_bound_ones():
    # D-31: ZC4P8R (PREMIUM_ECONOMY ticket, 800 − 500 = 300, CABIN_DOWNGRADE → review-level → NEEDS_REVIEW-bound) has the
    # bigger saving, but ZC3N1D (clean, 140 → REBOOK-bound) is served first and takes the only seat.
    review, clean = run([zc(pnr="ZC4P8R", cabin="PREMIUM_ECONOMY", price="800.00"), zc()], [zc_clean(seats=1)])
    assert (clean.action, clean.chosen_offer_id) == (Action.REBOOK, "OF-4001")
    assert (review.action, review.chosen_offer_id, review.confidence) == (Action.DO_NOT_REBOOK, None, Confidence.MEDIUM)
    assert set(review.reasons) == {Reason.SEAT_CONTENTION, Reason.CABIN_DOWNGRADE}


def test_ledger_ranks_bookings_by_their_preferred_offer():
    # D-31: rank by the counted net saving of the offer the booking would actually pick (clean first, D-29).
    # ZC3N1D with 0 bags: OF-4001 clean 640 − 590 = 50; OF-4007 (non-refundable, 0 bags) review-level 640 − 400 = 240.
    # ZC8B2K (1 bag): OF-4001 clean 690 − 590 = 100; OF-4007 has fewer bags → ineligible.
    # Both are REBOOK-bound; 100 > 50 → ZC8B2K takes the seat, ZC3N1D falls through to OF-4007 → NEEDS_REVIEW.
    offers = [zc_clean(price="590.00", seats=1), offer("OF-4001", offer_id="OF-4007", price="400.00", bags=0)]
    first, second = run([zc(bags=0), zc(pnr="ZC8B2K", price="690.00")], offers)
    assert (second.action, second.chosen_offer_id) == (Action.REBOOK, "OF-4001")
    assert (first.action, first.chosen_offer_id) == (Action.NEEDS_REVIEW, "OF-4007")
