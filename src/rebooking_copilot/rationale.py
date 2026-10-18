"""Template rationales: the full text in stub mode, and the code's own summary in front of the agent's view.

Every number comes from the recommendation's own breakdown or assessments, shown exactly (rounded only when
rounding changes nothing), so the text passes the same number check the agent's text must pass (D-25, D-41).
"""

from rebooking_copilot.money import Money
from rebooking_copilot.outcome import Action
from rebooking_copilot.policy import REVIEW_LEVEL_REASONS, Reason, Tier

_PHRASES = {
    Reason.FEWER_BAGS: "it includes fewer bags",
    Reason.SCHEDULE_OUTSIDE_WINDOW: "it departs too far from the booked time",
    Reason.ARRIVES_LATER_DAY: "it arrives a day later",
    Reason.INSUFFICIENT_SEATS: "it has too few seats",
    Reason.SEAT_CONTENTION: "its seats went to other bookings in this run",
    Reason.CURRENCY_MISMATCH_NO_FX: "no usable FX rate was available",
    Reason.DEPARTS_TOO_SOON: "it departs too soon to rebook safely",
    Reason.CABIN_DOWNGRADE: "it is a lower cabin or fare product",
    Reason.REFUNDABILITY_LOST: "the new fare is not refundable",
    Reason.CARRIER_CHANGE: "it is on another carrier",
    Reason.ADDED_STOP: "it adds a stop",
    Reason.DIFFERENT_FLIGHT: "it is a different flight",
    Reason.PRICE_ANOMALY: "its price is implausibly low (a possible feed error)",
}


def _m(money: Money) -> str:
    """Rounded to minor units when that is exact, otherwise the exact amount."""
    rounded = money.quantized()
    return str(rounded) if rounded.amount == money.amount else f"{money.amount.normalize():f} {money.currency}"


def _join(phrases: list[str]) -> str:
    return phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " and " + phrases[-1]


def _fx_clause(bd) -> str:
    if bd.fx is None:
        return ""
    return f" (converted from {_m(bd.offer_price_per_passenger)} at the {bd.fx.from_currency}→{bd.fx.to_currency} rate {bd.fx.rate}, source {bd.fx.source})"


def _saving_clause(bd) -> str:
    """The net saving, plus the counted saving when the settlement policy discounts credit."""
    text = f"after {_m(bd.change_fees)} in change fees the net saving is {_m(bd.net_saving)}"
    if bd.counted_net_saving != bd.net_saving:
        text += f", counted as {_m(bd.counted_net_saving)} under the settlement policy"
    return text


def _candidate_reasons(a) -> str:
    phrases = []
    for reason in a.reasons:
        if reason is Reason.NET_SAVING_BELOW_THRESHOLD and a.breakdown is not None:
            phrases.append(f"the counted saving of {_m(a.breakdown.counted_net_saving)} is below the {_m(a.breakdown.threshold)} threshold")
        elif reason in _PHRASES:
            phrases.append(_PHRASES[reason])
    return f"{a.offer_id}: {_join(phrases)}" if phrases else a.offer_id


def _tails(reasons: set) -> str:
    tail = ""
    if Reason.OFFER_DATA_REJECTED in reasons:
        tail += " An offer on this route was rejected as invalid data, so the picture is incomplete."
    if Reason.CANDIDATE_NOT_EVALUATED in reasons:
        tail += " Another offer on this route couldn't be priced (no usable FX rate), so the picture is incomplete."
    return tail


def explain(rec, *, agent: bool = False) -> str:
    """A short, human-readable reason for the recommendation, built only from its own fields."""
    reasons = set(rec.reasons)
    tail = _tails(reasons)
    review = [_PHRASES[r] for r in rec.reasons if r in REVIEW_LEVEL_REASONS]

    if Reason.EVALUATION_ERROR in reasons:
        return f"Not evaluated: an unexpected error occurred ({rec.error}). A human should check this booking."
    if rec.data_issues:
        details = "; ".join(f"{i.code}: {i.detail}" for i in rec.data_issues)
        return f"Not evaluated: the booking failed data checks ({details})."
    if Reason.NO_CANDIDATES in reasons:
        return "No offer in the snapshot matches this booking's route and date." + tail

    bd = rec.breakdown
    if rec.action is Action.REBOOK and bd is not None:
        traded = f" Trade-off: {_join(review)}." if review else ""
        credit = " The difference comes back as travel credit, counted under the active settlement policy." if Reason.SAVING_AS_CREDIT in reasons else ""
        return (
            f"Rebook to {rec.chosen_offer_id}: {_m(bd.offer_price_per_passenger_in_ticket_currency)} per passenger instead of "
            f"{_m(bd.paid_per_passenger)}{_fx_clause(bd)}; {_saving_clause(bd)}, at or above the {_m(bd.threshold)} threshold; "
            f"confidence {rec.confidence}.{traded}{credit}{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and Reason.LLM_DISAGREES_WITH_POLICY in reasons and bd is not None:
        return (
            f"The policy finds a clean saving on {rec.chosen_offer_id} ({_saving_clause(bd)}), but the agent advised "
            f"against it, so a human should decide.{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and Reason.SAVING_AS_CREDIT in reasons and bd is not None and not review:
        return (
            f"{rec.chosen_offer_id} is the same flight and product, {_m(bd.gross_saving)} cheaper in total{_fx_clause(bd)}; "
            f"{_saving_clause(bd)}. The ticket is non-refundable, so the difference would come back as travel credit, which "
            f"the cash-only policy doesn't count as a saving. A human should decide.{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and bd is not None:
        why = f", but {_join(review)}. That trade-off needs a human decision." if review else ". The agent asked a human to decide."
        return f"{rec.chosen_offer_id} would save {_m(bd.counted_net_saving)} net{_fx_clause(bd)}{why}{tail}"
    eligible = [a for a in rec.candidates if a.tier is not Tier.INELIGIBLE]
    if agent and eligible:
        offered = "; ".join(_candidate_reasons(a) for a in eligible)
        verdict = "declined the eligible offers" if rec.action is Action.DO_NOT_REBOOK else "asked a human to decide between the eligible offers"
        return f"The agent {verdict} ({offered}).{tail}"
    if rec.action is Action.NEEDS_REVIEW and Reason.CURRENCY_MISMATCH_NO_FX in reasons:
        return "An offer is priced in another currency and no usable FX rate was available, so the saving couldn't be computed." + tail
    if rec.candidates:
        return "No eligible offer. " + "; ".join(_candidate_reasons(a) for a in rec.candidates) + "." + tail
    return "No recommendation could be made." + tail
