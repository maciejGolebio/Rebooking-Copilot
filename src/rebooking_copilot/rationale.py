"""Template rationales for stub mode and fallbacks.

Every number comes from the recommendation's own breakdown or assessments, so the text is faithful by
construction (the same faithfulness check the agent's text must pass, D-25).
"""

from rebooking_copilot.outcome import Action
from rebooking_copilot.policy import REVIEW_LEVEL_REASONS, Reason

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


def _join(phrases: list[str]) -> str:
    return phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " and " + phrases[-1]


def _fx_clause(bd) -> str:
    if bd.fx is None:
        return ""
    return f" (converted from {bd.offer_price_per_passenger} at {bd.fx.rate} {bd.fx.from_currency}→{bd.fx.to_currency}, source {bd.fx.source})"


def _candidate_reasons(a) -> str:
    phrases = []
    for reason in a.reasons:
        if reason is Reason.NET_SAVING_BELOW_THRESHOLD and a.breakdown is not None:
            phrases.append(f"the net saving of {a.breakdown.counted_net_saving} is below the {a.breakdown.threshold} threshold")
        elif reason in _PHRASES:
            phrases.append(_PHRASES[reason])
    return f"{a.offer_id}: {_join(phrases)}" if phrases else a.offer_id


def explain(rec) -> str:
    """A short, human-readable reason for the recommendation, built only from its own fields."""
    reasons = set(rec.reasons)
    tail = " An offer on this route was rejected as invalid data, so the picture is incomplete." if Reason.OFFER_DATA_REJECTED in reasons else ""

    if Reason.EVALUATION_ERROR in reasons:
        return f"Not evaluated: an unexpected error occurred ({rec.error}). A human should check this booking."
    if rec.data_issues:
        details = "; ".join(f"{i.code}: {i.detail}" for i in rec.data_issues)
        return f"Not evaluated: the booking failed data checks ({details})."
    if Reason.NO_CANDIDATES in reasons:
        return "No offer in the snapshot matches this booking's route and date." + tail

    bd = rec.breakdown
    if rec.action is Action.REBOOK and bd is not None:
        credit = " The difference comes back as travel credit, counted under the active settlement policy." if Reason.SAVING_AS_CREDIT in reasons else ""
        return (
            f"Rebook to {rec.chosen_offer_id}: {bd.offer_price_per_passenger_in_ticket_currency} per passenger instead of "
            f"{bd.paid_per_passenger}{_fx_clause(bd)}. After {bd.change_fees} in change fees the net saving is "
            f"{bd.counted_net_saving}, above the {bd.threshold} threshold; confidence {rec.confidence}.{credit}{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and Reason.LLM_DISAGREES_WITH_POLICY in reasons and bd is not None:
        return (
            f"The policy finds a clean saving of {bd.counted_net_saving} on {rec.chosen_offer_id}, but the agent advised "
            f"against it, so a human should decide.{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and Reason.SAVING_AS_CREDIT in reasons and bd is not None:
        return (
            f"{rec.chosen_offer_id} is the same flight and product, {bd.gross_saving} cheaper in total{_fx_clause(bd)}; after "
            f"{bd.change_fees} in change fees the net saving is {bd.counted_net_saving}. The ticket is non-refundable, so the "
            f"difference would come back as travel credit, which the cash-only policy doesn't count as a saving. A human "
            f"should decide.{tail}"
        )
    review = [_PHRASES[r] for r in rec.reasons if r in REVIEW_LEVEL_REASONS]
    if rec.action is Action.NEEDS_REVIEW and review and bd is not None:
        return (
            f"{rec.chosen_offer_id} would save {bd.counted_net_saving} net{_fx_clause(bd)}, but {_join(review)}. That "
            f"trade-off needs a human decision.{tail}"
        )
    if rec.action is Action.NEEDS_REVIEW and Reason.CURRENCY_MISMATCH_NO_FX in reasons:
        return "An offer is priced in another currency and no usable FX rate was available, so the saving couldn't be computed." + tail
    if rec.candidates:
        return "No eligible offer. " + "; ".join(_candidate_reasons(a) for a in rec.candidates) + "." + tail
    return "No recommendation could be made." + tail
