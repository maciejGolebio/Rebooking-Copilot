"""Claude-mode contract: routing (D-21), what the agent sees, its tools, and the faithfulness check (D-25).

Nothing here imports an LLM library; `agent.py` does, lazily. The validator that turns an agent run into a
recommendation lives in `decision.py`, next to the deterministic rules it re-checks (D-07).
"""

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rebooking_copilot.models import Offer, Pnr
from rebooking_copilot.outcome import Confidence
from rebooking_copilot.policy import REVIEW_LEVEL_REASONS, Assessment, PolicyConfig, Tier

PROMPT_VERSION = "rebooking_agent_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"


class AgentDecision(StrEnum):
    REBOOK = "REBOOK"
    DO_NOT_REBOOK = "DO_NOT_REBOOK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AgentAnswer(BaseModel):
    """The arguments of `submit_recommendation`. No numeric fields: every amount comes from code (D-25)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chosen_offer_id: str | None
    decision: AgentDecision
    rationale: Annotated[str, Field(min_length=1, max_length=1500)]
    confidence_ceiling: Confidence


class AgentRun(BaseModel):
    """What one agent run produced: an answer or a failure, the tool trace, and every text the model was shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: AgentAnswer | None = None
    failure: str | None = None
    trace: tuple[str, ...] = ()
    seen_text: tuple[str, ...] = ()


class AgentCase(BaseModel):
    """One booking routed to the agent: its seat-feasible eligible offers (post-ledger) and the policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pnr: Pnr
    offers: tuple[Offer, ...]  # the eligible, seat-feasible offers, best first
    assessments: tuple[Assessment, ...]  # same order as offers
    seat_blocked: frozenset[str] = frozenset()  # eligible, but their seats went to other bookings
    policy: PolicyConfig


class Reasoner(Protocol):
    id: str
    prompt_version: str | None

    def run(self, case: AgentCase) -> AgentRun: ...


class UnavailableReasoner:
    """Claude mode was requested but can't run (no SDK, no credentials, ...). Every routed booking falls back."""

    prompt_version = None

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.id = "claude (unavailable)"

    def run(self, case: AgentCase) -> AgentRun:
        return AgentRun(failure=f"claude unavailable: {self.reason}")


def needs_agent(eligible: Iterable[Assessment]) -> bool:
    """D-21: the agent runs only where judgement pays: a review-level offer, or two or more eligible offers."""
    eligible = list(eligible)
    return any(a.tier is Tier.REVIEW_LEVEL for a in eligible) or len(eligible) >= 2


# --- what the model sees ----------------------------------------------------------------------------------------------

def build_facts(case: AgentCase) -> dict:
    segment, ticket = case.pnr.itinerary[0], case.pnr.ticket
    return {
        "booking": {
            "pnr": case.pnr.pnr,
            "passengers": case.pnr.passengers,
            "route": f"{segment.origin}-{segment.destination}",
            "carrier": segment.carrier,
            "flight": segment.flight_number,
            "departure_local": segment.departure.isoformat(),
            "arrival_local": segment.arrival.isoformat(),
            "stops": segment.stops,
            "cabin": ticket.cabin,
            "refundable": ticket.refundable,
            "included_bags": ticket.baggage_included_pieces,
            "paid_per_passenger": str(ticket.price_per_passenger),
            "total_paid": str(ticket.total_paid),
            "change_fee_per_passenger": str(ticket.change_fee_per_passenger),
        },
        "eligible_offers": [
            {
                "offer_id": o.offer_id,
                "tier": a.tier,
                "review_reasons": [r for r in a.reasons if r in REVIEW_LEVEL_REASONS],
                "carrier": o.carrier,
                "flight": o.flight_number,
                "departure_local": o.departure.isoformat(),
                "arrival_local": o.arrival.isoformat(),
                "stops": o.stops,
                "cabin": o.cabin,
                "refundable": o.refundable,
                "included_bags": o.baggage_included_pieces,
                "seats_available": o.seats_available,
                "price_per_passenger": str(o.price),
                "counted_net_saving": str(a.breakdown.counted_net_saving),
                "threshold": str(a.breakdown.threshold),
                "settlement": a.breakdown.settlement,
            }
            for o, a in zip(case.offers, case.assessments, strict=True)
        ],
        "policy": {
            "settlement_policy": case.policy.settlement_policy,
            "review_level_rebook_confidence_cap": "MEDIUM",
            "note": "Money, eligibility, seats and thresholds are already checked by code.",
        },
    }


def render_user_message(case: AgentCase) -> str:
    facts = json.dumps(build_facts(case), indent=2)
    return (
        f"<facts>\n{facts}\n</facts>\n\n"
        f"Booking {case.pnr.pnr}: choose among the eligible offers above (or none), then call submit_recommendation once."
    )


def call_tool(case: AgentCase, name: str, args: dict) -> str:
    """Read-only, id-only tools over this booking's data (D-25). Errors come back as data, never as an exception."""
    assessments = {a.offer_id: a for a in case.assessments}

    def error(message: str) -> str:
        return json.dumps({"error": message})

    if not isinstance(args, dict):
        return error("arguments must be an object")
    if name == "get_fx_rate":
        pair = (args.get("from_currency"), args.get("to_currency"))
        for a in case.assessments:
            fx = a.breakdown.fx
            if fx is not None and (fx.from_currency, fx.to_currency) == pair:
                return fx.model_dump_json(by_alias=True)
        return error(f"no FX rate was used for {pair[0]}→{pair[1]} in this booking")
    if args.get("pnr_id") != case.pnr.pnr:
        return error(f"unknown booking {args.get('pnr_id')!r}; this run covers {case.pnr.pnr} only")
    if name == "find_candidates":
        return json.dumps([{"offer_id": a.offer_id, "tier": a.tier} for a in case.assessments])
    offer_id = args.get("offer_id")
    if offer_id not in assessments:
        return error(f"{offer_id!r} is not an eligible offer for {case.pnr.pnr}")
    a = assessments[offer_id]
    if name == "check_policy":
        return json.dumps({
            "offer_id": a.offer_id,
            "tier": a.tier,
            "reasons": list(a.reasons),
            "rule_trace": [r.model_dump(mode="json") for r in a.rule_trace],
        })
    if name == "compute_saving":
        return a.breakdown.model_dump_json(by_alias=True)
    return error(f"unknown tool {name!r}")


# --- faithfulness ---------------------------------------------------------------------------------------------------

_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def is_faithful(rationale: str, seen: Iterable[str]) -> bool:
    """Every number in the rationale must appear in something the model was shown (D-25)."""
    allowed: set[Decimal] = set()
    for text in seen:
        allowed |= numbers_in(text)
    return numbers_in(rationale) <= allowed


def parse_answer(args: object) -> AgentAnswer | str:
    try:
        return AgentAnswer.model_validate(args)
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"invalid submission: {'.'.join(str(p) for p in first['loc']) or '<args>'}: {first['msg']}"
