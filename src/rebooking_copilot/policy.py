"""Policy v1: candidate matching, the money breakdown and eligibility tiers (ADR-0005, ADR-0006).

These are the deterministic core tools the agent will later call by id (ADR-0007): `find_candidates`,
`compute_saving`, `check_policy`, plus `assess` which combines the last two. Pure functions: no I/O, no clock.

Money (D-18, D-10, D-13, D-27): everything is expressed in the ticket's currency.
    gross  = (paid per passenger − offer per passenger converted to the ticket currency) × passengers
    fees   = the *existing ticket's* change fee per passenger × passengers
    net    = gross − fees
    settlement = CASH if the ticket is refundable, else CREDIT (assumption, D-10)
    counted net = net, except CREDIT under credit_discounted: gross × credit_discount_factor − fees
    threshold   = max(min_net_absolute, min_net_fraction × total paid)

Tiers (D-11, D-13, D-14, ADR-0005), each failing rule adds its reason:
    INELIGIBLE   FEWER_BAGS · SCHEDULE_OUTSIDE_WINDOW (|departure shift| > window) · ARRIVES_LATER_DAY ·
                 NET_SAVING_BELOW_THRESHOLD (counted net < threshold) · INSUFFICIENT_SEATS (seats < passengers) ·
                 CURRENCY_MISMATCH_NO_FX (no usable FX quote; breakdown is None) ·
                 DEPARTS_TOO_SOON (earliest possible departure, local time read as UTC+14, < as_of + min lead time; D-33)
    REVIEW_LEVEL CABIN_DOWNGRADE · REFUNDABILITY_LOST · CARRIER_CHANGE · ADDED_STOP · DIFFERENT_FLIGHT (within the window) ·
                 PRICE_ANOMALY (offer in ticket currency < paid × (1 − max plausible discount); D-34)
    CLEAN        none of the above
Any hard-block reason makes the tier INELIGIBLE; review-level reasons are still recorded on ineligible offers.
Every rule is evaluated (no short-circuit) and recorded in the rule trace; reasons are listed in `Reason` order.
DIFFERENT_FLIGHT applies only within the schedule window (outside it, SCHEDULE_OUTSIDE_WINDOW says it all). Without
a breakdown the threshold and price-plausibility rules cannot be evaluated: they are recorded as not passed, and
CURRENCY_MISMATCH_NO_FX is the reason. FX quotes are checked before use (D-35): the pair must match the request and the
quote must be within one reshop interval of as_of; a provider error counts as no usable quote.
FX_CONVERTED is decision-level and never appears on an assessment.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from rebooking_copilot.base import OutputModel

from rebooking_copilot.fx import FxProvider, FxQuote, FxQuoteInvalidError, FxUnavailableError, convert
from rebooking_copilot.models import Cabin, Offer, Pnr
from rebooking_copilot.money import Money, in_money_context

CABIN_RANK: dict[Cabin, int] = {
    Cabin.BASIC_ECONOMY: 0,
    Cabin.ECONOMY: 1,
    Cabin.PREMIUM_ECONOMY: 2,
    Cabin.BUSINESS: 3,
    Cabin.FIRST: 4,
}


class SettlementPolicy(StrEnum):
    CASH_ONLY = "cash_only"
    CREDIT_FACE_VALUE = "credit_face_value"
    CREDIT_DISCOUNTED = "credit_discounted"


class Settlement(StrEnum):
    CASH = "CASH"
    CREDIT = "CREDIT"


class Tier(StrEnum):
    INELIGIBLE = "INELIGIBLE"
    REVIEW_LEVEL = "REVIEW_LEVEL"
    CLEAN = "CLEAN"


class Reason(StrEnum):
    # hard blocks → INELIGIBLE
    FEWER_BAGS = "FEWER_BAGS"
    SCHEDULE_OUTSIDE_WINDOW = "SCHEDULE_OUTSIDE_WINDOW"
    ARRIVES_LATER_DAY = "ARRIVES_LATER_DAY"
    NET_SAVING_BELOW_THRESHOLD = "NET_SAVING_BELOW_THRESHOLD"
    INSUFFICIENT_SEATS = "INSUFFICIENT_SEATS"
    SEAT_CONTENTION = "SEAT_CONTENTION"
    CURRENCY_MISMATCH_NO_FX = "CURRENCY_MISMATCH_NO_FX"
    DEPARTS_TOO_SOON = "DEPARTS_TOO_SOON"
    # review-level
    CABIN_DOWNGRADE = "CABIN_DOWNGRADE"
    REFUNDABILITY_LOST = "REFUNDABILITY_LOST"
    CARRIER_CHANGE = "CARRIER_CHANGE"
    ADDED_STOP = "ADDED_STOP"
    DIFFERENT_FLIGHT = "DIFFERENT_FLIGHT"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    # decision-level / informational
    FX_CONVERTED = "FX_CONVERTED"
    SAVING_AS_CREDIT = "SAVING_AS_CREDIT"
    NO_CANDIDATES = "NO_CANDIDATES"
    DATA_INVALID = "DATA_INVALID"
    DATA_INCONSISTENT = "DATA_INCONSISTENT"
    UNSUPPORTED_ITINERARY = "UNSUPPORTED_ITINERARY"
    OFFER_DATA_REJECTED = "OFFER_DATA_REJECTED"  # a matching offer was rejected as bad data: the picture is incomplete
    EVALUATION_ERROR = "EVALUATION_ERROR"  # unexpected failure while evaluating this booking; abstain
    LLM_DISAGREES_WITH_POLICY = "LLM_DISAGREES_WITH_POLICY"  # the agent declined a clean saving the policy approves (D-22)
    CANDIDATE_NOT_EVALUATED = "CANDIDATE_NOT_EVALUATED"  # another offer on the route had no usable FX rate (D-41)


HARD_BLOCKS = frozenset({
    Reason.FEWER_BAGS, Reason.SCHEDULE_OUTSIDE_WINDOW, Reason.ARRIVES_LATER_DAY, Reason.NET_SAVING_BELOW_THRESHOLD,
    Reason.INSUFFICIENT_SEATS, Reason.SEAT_CONTENTION, Reason.CURRENCY_MISMATCH_NO_FX, Reason.DEPARTS_TOO_SOON,
})
REVIEW_LEVEL_REASONS = frozenset({
    Reason.CABIN_DOWNGRADE, Reason.REFUNDABILITY_LOST, Reason.CARRIER_CHANGE, Reason.ADDED_STOP, Reason.DIFFERENT_FLIGHT,
    Reason.PRICE_ANOMALY,
})


class PolicyConfig(OutputModel):

    version: str = "v1"
    min_net_absolute: Decimal = Decimal("25")
    min_net_fraction: Decimal = Decimal("0.05")
    schedule_window: timedelta = timedelta(minutes=60)
    settlement_policy: SettlementPolicy = SettlementPolicy.CASH_ONLY
    credit_discount_factor: Decimal = Decimal("0.70")
    reshop_interval: timedelta = timedelta(days=1)
    confidence_margin_multiple: Decimal = Decimal("2")
    min_lead_time: timedelta = timedelta(hours=24)  # D-33
    max_utc_offset: timedelta = timedelta(hours=14)  # local times carry no zone: assume the earliest one (UTC+14)
    max_plausible_discount: Decimal = Decimal("0.60")  # D-34


DEFAULT_POLICY = PolicyConfig()


class Breakdown(OutputModel):
    """Every number in a recommendation comes from here; all amounts in the ticket's currency unless named otherwise."""

    passengers: int
    paid_per_passenger: Money
    offer_price_per_passenger: Money  # as quoted, in the offer's currency
    offer_price_per_passenger_in_ticket_currency: Money
    fx: FxQuote | None  # None when no conversion was needed
    gross_saving: Money
    change_fees: Money
    net_saving: Money
    settlement: Settlement
    counted_net_saving: Money
    threshold: Money


class RuleResult(OutputModel):

    rule: str
    passed: bool
    detail: str


class Assessment(OutputModel):

    offer_id: str
    tier: Tier
    reasons: tuple[Reason, ...]  # in the order of the rules, deduplicated
    breakdown: Breakdown | None  # None only for CURRENCY_MISMATCH_NO_FX
    rule_trace: tuple[RuleResult, ...]
    schedule_shift_minutes: int  # signed: offer departure − booked departure
    seats_available: int


_REASON_ORDER = {reason: i for i, reason in enumerate(Reason)}


def ordered(reasons) -> tuple[Reason, ...]:
    """Deduplicated, in `Reason` order."""
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


def find_candidates(pnr: Pnr, offers: tuple[Offer, ...]) -> tuple[Offer, ...]:
    """Offers on the same origin, destination and departure date as the booking's (single) segment, in input order."""
    segment = pnr.itinerary[0]
    return tuple(
        o for o in offers
        if (o.route.origin, o.route.destination, o.route.departure_date) == (segment.origin, segment.destination, segment.departure.date())
    )


@in_money_context
def compute_saving(pnr: Pnr, offer: Offer, *, fx: FxProvider, as_of: datetime, policy: PolicyConfig = DEFAULT_POLICY) -> Breakdown:
    """The money breakdown described in the module docstring. Raises FxUnavailableError when no rate exists."""
    ticket = pnr.ticket
    currency = ticket.price_per_passenger.currency
    quote: FxQuote | None = None
    offer_in_ticket_currency = offer.price
    if offer.price.currency != currency:
        quote = _usable_quote(fx, offer.price.currency, currency, as_of, policy)
        offer_in_ticket_currency = convert(offer.price, quote)
    gross = (ticket.price_per_passenger - offer_in_ticket_currency) * pnr.passengers
    fees = ticket.change_fee_per_passenger * pnr.passengers
    net = gross - fees
    settlement = Settlement.CASH if ticket.refundable else Settlement.CREDIT
    if settlement is Settlement.CREDIT and policy.settlement_policy is SettlementPolicy.CREDIT_DISCOUNTED:
        counted = gross * policy.credit_discount_factor - fees
    else:
        counted = net
    threshold = Money(amount=max(policy.min_net_absolute, policy.min_net_fraction * ticket.total_paid.amount), currency=currency)
    return Breakdown(
        passengers=pnr.passengers,
        paid_per_passenger=ticket.price_per_passenger,
        offer_price_per_passenger=offer.price,
        offer_price_per_passenger_in_ticket_currency=offer_in_ticket_currency,
        fx=quote,
        gross_saving=gross,
        change_fees=fees,
        net_saving=net,
        settlement=settlement,
        counted_net_saving=counted,
        threshold=threshold,
    )


@in_money_context
def check_policy(
    pnr: Pnr, offer: Offer, breakdown: Breakdown | None, policy: PolicyConfig = DEFAULT_POLICY, *, as_of: datetime, fx_detail: str | None = None
) -> Assessment:
    """Tier, reasons and rule trace for one offer. `breakdown=None` means the saving could not be computed (no usable FX)."""
    segment, ticket = pnr.itinerary[0], pnr.ticket
    shift = int((offer.departure - segment.departure).total_seconds() // 60)
    window = int(policy.schedule_window.total_seconds() // 60)
    within_window = abs(shift) <= window
    same_flight = (offer.carrier, offer.flight_number) == (segment.carrier, segment.flight_number)
    if breakdown is None:
        threshold_rule = (False, "not evaluated: no FX rate for the offer currency", None)
    else:
        passes = breakdown.counted_net_saving >= breakdown.threshold
        threshold_rule = (passes, f"counted net {breakdown.counted_net_saving} vs threshold {breakdown.threshold}", Reason.NET_SAVING_BELOW_THRESHOLD)
    if breakdown is None:
        plausibility_rule = (False, "not evaluated: no FX rate for the offer currency", None)
    else:
        floor = breakdown.paid_per_passenger * (1 - policy.max_plausible_discount)
        plausibility_rule = (
            breakdown.offer_price_per_passenger_in_ticket_currency >= floor,
            f"offer {breakdown.offer_price_per_passenger_in_ticket_currency} vs plausibility floor {floor}",
            Reason.PRICE_ANOMALY,
        )
    earliest_departure = offer.departure.replace(tzinfo=UTC) - policy.max_utc_offset
    lead = earliest_departure - as_of

    rules = [
        ("baggage", offer.baggage_included_pieces >= ticket.baggage_included_pieces,
         f"offer {offer.baggage_included_pieces} vs booked {ticket.baggage_included_pieces} bags", Reason.FEWER_BAGS),
        ("schedule_window", within_window, f"departure shift {shift:+d} min, window ±{window} min", Reason.SCHEDULE_OUTSIDE_WINDOW),
        ("arrival_day", offer.arrival.date() <= segment.arrival.date(),
         f"arrives {offer.arrival.date()} vs booked {segment.arrival.date()}", Reason.ARRIVES_LATER_DAY),
        ("net_saving_threshold", *threshold_rule),
        ("seats", offer.seats_available >= pnr.passengers,
         f"{offer.seats_available} seats for {pnr.passengers} passengers", Reason.INSUFFICIENT_SEATS),
        ("fx_rate", breakdown is not None,
         "comparable" if breakdown is not None else (fx_detail or f"no {offer.price.currency}→{ticket.price_per_passenger.currency} rate"),
         Reason.CURRENCY_MISMATCH_NO_FX),
        ("lead_time", lead >= policy.min_lead_time,
         f"earliest possible departure {lead} after as_of, minimum {policy.min_lead_time}", Reason.DEPARTS_TOO_SOON),
        ("cabin", CABIN_RANK[offer.cabin] >= CABIN_RANK[ticket.cabin], f"offer {offer.cabin} vs booked {ticket.cabin}", Reason.CABIN_DOWNGRADE),
        ("refundability", offer.refundable or not ticket.refundable,
         f"offer refundable={offer.refundable}, booked refundable={ticket.refundable}", Reason.REFUNDABILITY_LOST),
        ("carrier", offer.carrier == segment.carrier, f"offer {offer.carrier} vs booked {segment.carrier}", Reason.CARRIER_CHANGE),
        ("stops", offer.stops <= segment.stops, f"offer {offer.stops} vs booked {segment.stops} stops", Reason.ADDED_STOP),
        ("same_flight", same_flight or not within_window,
         f"offer {offer.flight_number} vs booked {segment.flight_number}", Reason.DIFFERENT_FLIGHT),
        ("price_plausibility", *plausibility_rule),
    ]
    trace = tuple(RuleResult(rule=name, passed=passed, detail=detail) for name, passed, detail, _ in rules)
    reasons = ordered(reason for _, passed, _, reason in rules if not passed and reason is not None)
    if set(reasons) & HARD_BLOCKS:
        tier = Tier.INELIGIBLE
    elif set(reasons) & REVIEW_LEVEL_REASONS:
        tier = Tier.REVIEW_LEVEL
    else:
        tier = Tier.CLEAN
    return Assessment(
        offer_id=offer.offer_id,
        tier=tier,
        reasons=reasons,
        breakdown=breakdown,
        rule_trace=trace,
        schedule_shift_minutes=shift,
        seats_available=offer.seats_available,
    )


def assess(pnr: Pnr, offer: Offer, *, fx: FxProvider, as_of: datetime, policy: PolicyConfig = DEFAULT_POLICY) -> Assessment:
    """compute_saving + check_policy; FxUnavailableError becomes an INELIGIBLE assessment with CURRENCY_MISMATCH_NO_FX."""
    try:
        breakdown, fx_detail = compute_saving(pnr, offer, fx=fx, as_of=as_of, policy=policy), None
    except FxUnavailableError as exc:
        breakdown, fx_detail = None, str(exc)
    return check_policy(pnr, offer, breakdown, policy, as_of=as_of, fx_detail=fx_detail)


def _usable_quote(fx: FxProvider, from_currency: str, to_currency: str, as_of: datetime, policy: PolicyConfig) -> FxQuote:
    """Ask the provider and check the answer (D-35). Raises FxUnavailableError / FxQuoteInvalidError, never anything else."""
    try:
        quote = fx.quote(from_currency, to_currency, as_of)
    except FxUnavailableError:
        raise
    except Exception as exc:  # a real API can time out or fail in many ways; none of them may crash the run
        raise FxQuoteInvalidError(f"FX provider error: {type(exc).__name__}: {exc}") from exc
    if not isinstance(quote, FxQuote) or (quote.from_currency, quote.to_currency) != (from_currency, to_currency):
        raise FxQuoteInvalidError(f"FX quote does not answer {from_currency}→{to_currency}")
    if abs(as_of - quote.as_of) > policy.reshop_interval:
        raise FxQuoteInvalidError(f"FX quote as of {quote.as_of.isoformat()} is more than {policy.reshop_interval} from as_of")
    return quote
