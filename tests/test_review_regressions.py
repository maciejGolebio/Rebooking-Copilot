"""Regression tests for the money-safety review of /slice decision (findings 1-10; decisions D-33, D-34, D-35).

Each test reproduces the reviewer's failure scenario and asserts the safe outcome. Expected values are written out
next to each case.
"""

import copy
import decimal
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from factories import CAPTURED_AT, booking, fixture_inputs, load, offer, raw, usd
from rebooking_copilot.decision import Action, Confidence, evaluate
from rebooking_copilot.fx import FxQuote, MockFxProvider
from rebooking_copilot.loader import IssueCode, parse_fare_snapshot, parse_pnrs
from rebooking_copilot.policy import Reason, Tier


def zc(**edits) -> dict:
    """ZC3N1D: 1 pax, 640 USD, refundable, fee 0, MIA→BOG 2026-10-10 22:05."""
    return booking("ZC3N1D", **edits)


def zc_clean(**edits) -> dict:
    """OF-4001 made refundable → CLEAN for ZC3N1D; 500 USD → net 140."""
    return offer("OF-4001", refundable=True, **edits)


def run_raw(bookings: list[dict], offers: list[dict], **kwargs):
    """Like factories.load + evaluate, but lets rejected records through (they are the point here)."""
    return evaluate(parse_pnrs({"pnrs": bookings}), parse_fare_snapshot({"capturedAt": "2026-07-08T09:00:00Z", "offers": offers}), **kwargs)


def summary(rec) -> tuple:
    return rec.action, rec.chosen_offer_id, rec.estimated_net_saving, rec.confidence, rec.reasons


# --- 1 (critical): duplicate offer ids must not let the ledger oversell -------------------------------------------

def test_duplicate_offer_ids_are_rejected_and_never_rebooked():
    # Two different offers share id OF-X (9 seats and 1 seat). Before the fix the ledger took 9 seats from the first
    # and sold the 1-seat offer twice. Now both copies are DATA_INCONSISTENT and every booking on the route abstains.
    offers = [zc_clean(offer_id="OF-X", seats=9), zc_clean(offer_id="OF-X", seats=1)]
    bookings = [zc(pnr="ZCXXXX"), zc(pnr="ZCYYYY"), zc(pnr="ZCZZZZ")]
    snapshot = parse_fare_snapshot({"capturedAt": "2026-07-08T09:00:00Z", "offers": offers})
    assert snapshot.offers == () and [r.offer_id for r in snapshot.rejected] == ["OF-X", "OF-X"]
    assert all(IssueCode.DATA_INCONSISTENT in {i.code for i in r.issues} for r in snapshot.rejected)
    recs = evaluate(parse_pnrs({"pnrs": bookings}), snapshot)
    assert all(r.action is Action.NEEDS_REVIEW and Reason.OFFER_DATA_REJECTED in r.reasons for r in recs)


# --- 2 (high): a duplicated booking must not be rebooked twice --------------------------------------------------------

def test_duplicate_pnr_locators_are_rejected():
    pnr_load = parse_pnrs({"pnrs": [zc(), zc()]})
    assert pnr_load.pnrs == () and [r.index for r in pnr_load.rejected] == [0, 1]
    recs = evaluate(pnr_load, load([], [zc_clean(seats=5)])[1])
    assert [summary(r)[:2] for r in recs] == [(Action.NEEDS_REVIEW, None)] * 2
    assert all(r.reasons == (Reason.DATA_INCONSISTENT,) for r in recs)


# --- 3 (high): the FX seam is not trusted blindly -------------------------------------------------------------------

class _Provider:
    def __init__(self, answer):
        self.answer = answer

    def quote(self, from_currency, to_currency, as_of):
        return self.answer(from_currency, to_currency, as_of)


def _timeout(*_):
    raise TimeoutError("FX API did not answer in 2 s")


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(lambda f, t, a: FxQuote(from_currency=f, to_currency="GBP", rate=Decimal("0.79"), as_of=a, source="bad"), id="wrong-pair"),
        pytest.param(_timeout, id="timeout"),
        pytest.param(lambda f, t, a: FxQuote(from_currency=f, to_currency=t, rate=Decimal("0"), as_of=a, source="bad"), id="zero-rate"),
        pytest.param(lambda f, t, a: FxQuote(from_currency=f, to_currency=t, rate=Decimal("-0.9"), as_of=a, source="bad"), id="negative-rate"),
        pytest.param(lambda f, t, a: FxQuote(from_currency=f, to_currency=t, rate=Decimal("0.9276"), as_of=datetime(2020, 1, 1, tzinfo=UTC), source="old"), id="stale-quote"),
    ],
)
def test_unusable_fx_quotes_abstain_without_crashing_the_run(answer):
    # Before the fix: crash (wrong pair, timeout, zero rate) or REBOOK 4090 EUR (negative rate) or an accepted 2020 quote.
    recs = {r.pnr: r for r in evaluate(*fixture_inputs(), fx=_Provider(answer))}
    rt = recs["RT5K8B"]
    assert summary(rt) == (Action.NEEDS_REVIEW, None, None, Confidence.LOW, (Reason.CURRENCY_MISMATCH_NO_FX,))
    assert rt.candidates[0].breakdown is None
    assert not next(r for r in rt.candidates[0].rule_trace if r.rule == "fx_rate").passed
    golden = {r.pnr: r for r in evaluate(*fixture_inputs())}
    for locator in ["QX7T2A", "LM9P4C", "ZC3N1D", "HB6W9E"]:  # USD-only bookings never ask the provider
        assert summary(recs[locator]) == summary(golden[locator])


# --- 4 (high): never rebook onto a departed or imminent flight (D-33) ----------------------------------------------

def test_running_after_departure_never_rebooks():
    # as_of = 2026-10-18: every fixture flight has left. Before: RT5K8B REBOOK (LOW).
    recs = evaluate(*fixture_inputs(), as_of=datetime(2026, 10, 18, tzinfo=UTC))
    assert all(r.action is not Action.REBOOK for r in recs)
    rt = next(r for r in recs if r.pnr == "RT5K8B")
    assert (rt.action, rt.confidence) == (Action.DO_NOT_REBOOK, Confidence.HIGH)
    assert Reason.DEPARTS_TOO_SOON in rt.reasons


@pytest.mark.parametrize("extra, eligible", [(timedelta(0), True), (timedelta(minutes=1), False)])
def test_lead_time_boundary(extra, eligible):
    # OF-4001 departs 2026-10-10 22:05 local; read as UTC+14 that is 08:05Z at the earliest. With 24 h lead time the
    # last eligible as_of is 2026-10-09T08:05Z (lead exactly 24 h, "≥" passes).
    as_of = datetime(2026, 10, 9, 8, 5, tzinfo=UTC) + extra
    (rec,) = evaluate(*load([zc()], [zc_clean()]), as_of=as_of)
    (a,) = rec.candidates
    assert (Reason.DEPARTS_TOO_SOON not in a.reasons) is eligible
    assert (a.tier is Tier.CLEAN) is eligible


def test_as_of_must_be_aware_and_not_before_the_snapshot():
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate(*fixture_inputs(), as_of=datetime(2026, 7, 8, 9, 0))
    with pytest.raises(ValueError, match="earlier than the snapshot"):
        evaluate(*fixture_inputs(), as_of=CAPTURED_AT - timedelta(seconds=1))


# --- 5 (medium): seats freed by a displacement are offered again ---------------------------------------------------

def test_seats_freed_by_displacement_are_reoffered():
    # One clean offer, 4 seats, input order B, C, A:
    #   B: 3 pax × (560 − 500) = 180 · C: 2 pax × (580 − 500) = 160 · A: 2 pax × (640 − 500) = 280.
    # B is held, C is rejected (3 + 2 > 4), A displaces B (2 + 3 > 4). Before the fix C stayed out with 2 seats free.
    # Now: A and C REBOOK (4 seats), B SEAT_CONTENTION.
    bookings = [zc(pnr="ZCBBBB", passengers=3, price="560.00"), zc(pnr="ZCCCCC", passengers=2, price="580.00"), zc(pnr="ZCAAAA", passengers=2)]
    b, c, a = evaluate(*load(bookings, [zc_clean(seats=4)]))
    assert summary(a)[:3] == (Action.REBOOK, "OF-4001", usd("280.00"))
    assert summary(c)[:3] == (Action.REBOOK, "OF-4001", usd("160.00"))
    assert summary(b) == (Action.DO_NOT_REBOOK, None, None, Confidence.MEDIUM, (Reason.SEAT_CONTENTION,))


# --- 6 (medium): implausible prices -------------------------------------------------------------------------------------

def test_zero_price_offer_is_invalid_data():
    (rec,) = run_raw([zc()], [zc_clean(price="0.00")])
    assert summary(rec) == (Action.NEEDS_REVIEW, None, None, Confidence.LOW, (Reason.NO_CANDIDATES, Reason.OFFER_DATA_REJECTED))


@pytest.mark.parametrize("price, anomalous", [("256.00", False), ("255.99", True)])
def test_price_anomaly_boundary(price, anomalous):
    # D-34: floor = 640 × (1 − 0.60) = 256. At 256 the offer is CLEAN; one cent below it is review-level → NEEDS_REVIEW.
    (rec,) = evaluate(*load([zc()], [zc_clean(price=price)]))
    (a,) = rec.candidates
    assert (Reason.PRICE_ANOMALY in a.reasons) is anomalous
    assert rec.action is (Action.NEEDS_REVIEW if anomalous else Action.REBOOK)


# --- 7 (medium): a rejected offer on the route means the picture is incomplete ------------------------------------

def _broken_offer(**edits) -> dict:
    record = zc_clean(**edits)
    record["changeFeePerPassenger"]["currency"] = "EUR"  # price USD, fee EUR → DATA_INCONSISTENT
    return record


def test_only_offer_rejected_means_needs_review_not_a_confident_no():
    # Before: DO_NOT_REBOOK / NO_CANDIDATES / HIGH, although the route's only offer just failed validation.
    (rec,) = run_raw([zc()], [_broken_offer()])
    assert summary(rec) == (Action.NEEDS_REVIEW, None, None, Confidence.LOW, (Reason.NO_CANDIDATES, Reason.OFFER_DATA_REJECTED))


def test_a_rejected_sibling_offer_lowers_rebook_confidence():
    # A valid clean offer (140 ≥ 64 → HIGH) plus a rejected offer on the same route → REBOOK, one band lower.
    (rec,) = run_raw([zc()], [zc_clean(), _broken_offer(offer_id="OF-4999")])
    assert summary(rec) == (Action.REBOOK, "OF-4001", usd("140.00"), Confidence.MEDIUM, (Reason.OFFER_DATA_REJECTED,))


def test_rejected_offers_on_other_routes_do_not_matter():
    data = raw("fares_feed.json")
    data["offers"][0]["price"]["amount"] = Decimal("0")  # OF-1001 (JFK→LAX) becomes invalid
    recs = {r.pnr: r for r in evaluate(fixture_inputs()[0], parse_fare_snapshot(data))}
    golden = {r.pnr: r for r in evaluate(*fixture_inputs())}
    assert Reason.OFFER_DATA_REJECTED in recs["QX7T2A"].reasons
    for locator in ["LM9P4C", "RT5K8B", "ZC3N1D", "HB6W9E"]:
        assert summary(recs[locator]) == summary(golden[locator])


# --- 8 (low): extreme amounts and the global Decimal context ------------------------------------------------------

def test_absurd_amounts_are_rejected_as_data_not_crashes():
    huge_offer = zc_clean()
    huge_offer["price"]["amount"] = Decimal("9E+999999")
    huge_ticket = zc(pnr="ZCHUGE", price="1E+27")
    pnr_load = parse_pnrs({"pnrs": [huge_ticket, zc()]})
    snapshot = parse_fare_snapshot({"capturedAt": "2026-07-08T09:00:00Z", "offers": [huge_offer]})
    assert [r.pnr for r in pnr_load.rejected] == ["ZCHUGE"]
    assert [r.offer_id for r in snapshot.rejected] == ["OF-4001"]
    recs = evaluate(pnr_load, snapshot)
    assert [r.action for r in recs] == [Action.NEEDS_REVIEW, Action.NEEDS_REVIEW]


def test_results_do_not_depend_on_the_callers_decimal_context():
    golden = [summary(r) for r in evaluate(*fixture_inputs())]
    with decimal.localcontext() as ctx:
        ctx.prec = 3
        assert [summary(r) for r in evaluate(*fixture_inputs())] == golden


# --- 9 (low): the fingerprint covers the snapshot capture time --------------------------------------------------------

def test_fingerprint_changes_with_captured_at():
    pnr_load = fixture_inputs()[0]
    fresh = raw("fares_feed.json")
    older = copy.deepcopy(fresh)
    older["capturedAt"] = "2026-06-08T09:00:00Z"
    as_of = CAPTURED_AT
    a = evaluate(pnr_load, parse_fare_snapshot(fresh), as_of=as_of)
    b = evaluate(pnr_load, parse_fare_snapshot(older), as_of=as_of)
    assert all(x.fingerprint != y.fingerprint for x, y in zip(a, b, strict=True))


# --- 10 (low): "a higher price never moves toward REBOOK" holds per booking, not across bookings ---------------------

def test_price_raise_can_reorder_bookings_in_the_ledger():
    # Documented D-31 consequence, not a money-safety violation. Offer with 2 seats:
    #   at 500: ZCMMMM 2 pax × (600 − 500) = 200 > ZC3N1D 140 → ZCMMMM takes both seats, ZC3N1D SEAT_CONTENTION.
    #   at 570: ZCMMMM 2 × 30 = 60 ≥ max(25, 5% × 1200) = 60; ZC3N1D 70 > 60 → ZC3N1D first (1 seat), ZCMMMM needs 2 → contention.
    # ZC3N1D moves from DO_NOT_REBOOK to REBOOK although the price went up; for ZCMMMM itself the invariant holds.
    bookings = [zc(pnr="ZCMMMM", passengers=2, price="600.00"), zc()]
    m_low, z_low = evaluate(*load(bookings, [zc_clean(seats=2)]))
    m_high, z_high = evaluate(*load(bookings, [zc_clean(seats=2, price="570.00")]))
    assert (m_low.action, z_low.action) == (Action.REBOOK, Action.DO_NOT_REBOOK)
    assert (m_high.action, z_high.action) == (Action.DO_NOT_REBOOK, Action.REBOOK)
    assert z_high.estimated_net_saving == usd("70.00")
