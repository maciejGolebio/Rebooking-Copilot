"""Claude-mode contract: routing (D-21), what the agent sees, its tools, and the number check on its text (D-25, D-41).

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
from rebooking_copilot.money import MINOR_UNITS, Money
from rebooking_copilot.outcome import Confidence
from rebooking_copilot.policy import REVIEW_LEVEL_REASONS, Assessment, PolicyConfig, Tier

PROMPT_VERSION = "rebooking_agent_v2"
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
    """What one agent run produced: an answer or a failure, the tool trace, and one line per model call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: AgentAnswer | None = None
    failure: str | None = None
    trace: tuple[str, ...] = ()  # tool calls, in order
    calls: tuple[str, ...] = ()  # per model call: serving model, stop reason, tokens, latency
    served_model: str | None = None  # the model that produced the final reply (can differ after a refusal fallback)


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
    """Claude mode was requested but can't run (no SDK, no key, ...). Every routed booking falls back."""

    prompt_version = None
    config: dict = {}

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

def _json(obj, **kwargs) -> str:
    """JSON for the model. `<` and `>` are escaped, so no value can close the <facts> delimiter (D-41)."""
    return json.dumps(obj, **kwargs).replace("<", "\\u003c").replace(">", "\\u003e")


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
    return (
        f"<facts>\n{_json(build_facts(case), indent=2)}\n</facts>\n\n"
        f"Booking {case.pnr.pnr}: choose among the eligible offers above (or none), then call submit_recommendation once."
    )


def call_tool(case: AgentCase, name: str, args: dict) -> tuple[str, bool]:
    """Read-only, id-only tools over this booking's data (D-25). Returns (content, is_error); never raises."""
    assessments = {a.offer_id: a for a in case.assessments}

    def error(message: str) -> tuple[str, bool]:
        return _json({"error": message}), True

    if not isinstance(args, dict):
        return error("arguments must be an object")
    if name == "get_fx_rate":
        pair = (args.get("from_currency"), args.get("to_currency"))
        for a in case.assessments:
            fx = a.breakdown.fx
            if fx is not None and (fx.from_currency, fx.to_currency) == pair:
                return _json(fx.model_dump(mode="json", by_alias=True)), False
        return error("no FX rate was used for that currency pair in this booking")
    if args.get("pnr_id") != case.pnr.pnr:
        return error(f"unknown booking; this run covers {case.pnr.pnr} only")
    if name == "find_candidates":
        return _json([{"offer_id": a.offer_id, "tier": a.tier} for a in case.assessments]), False
    offer_id = args.get("offer_id")
    if offer_id not in assessments:
        return error(f"not an eligible offer for {case.pnr.pnr}; see FACTS for the eligible offer ids")
    a = assessments[offer_id]
    if name == "check_policy":
        return _json({
            "offer_id": a.offer_id,
            "tier": a.tier,
            "reasons": list(a.reasons),
            "rule_trace": [r.model_dump(mode="json") for r in a.rule_trace],
        }), False
    if name == "compute_saving":
        return _json(a.breakdown.model_dump(mode="json", by_alias=True)), False
    return error("unknown tool")


# --- the number check (D-25, D-41) ---------------------------------------------------------------------------------

_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_CURRENCIES = "|".join(sorted(MINOR_UNITS))
_AMOUNT = r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?"
_MONEY = re.compile(rf"(?<![\w.])(?P<a>{_AMOUNT})\s?(?P<c1>{_CURRENCIES})\b|\b(?P<c2>{_CURRENCIES})\s?(?P<b>{_AMOUNT})(?![\w.])")
_NUMBER_WORDS = re.compile(
    r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|dozen|half|quarter)\b",
    re.IGNORECASE,
)


class AllowedNumbers(BaseModel):
    """Numbers a rationale may contain: money only as exact (amount, currency) pairs from code, a few plain counts,
    and identifier tokens (ids, flight numbers, dates, times) that are stripped before checking."""

    model_config = ConfigDict(frozen=True)

    money: frozenset[tuple[Decimal, str]]
    plain: frozenset[Decimal]
    tokens: tuple[str, ...]


def numbers_in(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _breakdown_money(bd) -> list[Money]:
    return [bd.paid_per_passenger, bd.offer_price_per_passenger, bd.offer_price_per_passenger_in_ticket_currency,
            bd.gross_saving, bd.change_fees, bd.net_saving, bd.counted_net_saving, bd.threshold]


def _money_in(text: str) -> set[tuple[Decimal, str]]:
    pairs = set()
    for match in _MONEY.finditer(text):
        amount, currency = match.group("a") or match.group("b"), match.group("c1") or match.group("c2")
        pairs.add((Decimal(amount.replace(",", "")), currency))
    return pairs


def _time_tokens(dt) -> list[str]:
    iso = dt.isoformat()
    return [iso, iso[:10], iso[11:16], iso[11:19]]


def allowed_for_case(case: AgentCase) -> AllowedNumbers:
    ticket, segment = case.pnr.ticket, case.pnr.itinerary[0]
    money = [ticket.price_per_passenger, ticket.total_paid, ticket.change_fee_per_passenger]
    plain = {Decimal(case.pnr.passengers), Decimal(ticket.baggage_included_pieces), Decimal(segment.stops),
             Decimal(int(case.policy.schedule_window.total_seconds() // 60)), Decimal(int(case.policy.min_lead_time.total_seconds() // 3600))}
    tokens = [case.pnr.pnr, segment.flight_number, segment.carrier, *_time_tokens(segment.departure), *_time_tokens(segment.arrival)]
    for o, a in zip(case.offers, case.assessments, strict=True):
        money += _breakdown_money(a.breakdown)
        plain |= {Decimal(o.seats_available), Decimal(o.baggage_included_pieces), Decimal(o.stops), Decimal(abs(a.schedule_shift_minutes))}
        tokens += [o.offer_id, o.flight_number, o.carrier, *_time_tokens(o.departure), *_time_tokens(o.arrival)]
        if a.breakdown.fx is not None:
            plain.add(a.breakdown.fx.rate)
            tokens.append(a.breakdown.fx.source)
    # FACTS shows these amounts rounded to minor units (str(Money), see build_facts); the tools return them exact. Both
    # are what the model was shown. The rounded values come from the amounts themselves, not from scanning the rendered
    # text, so a money-like offer id ("999.00USD") can't add an amount.
    in_facts = [ticket.price_per_passenger, ticket.total_paid, ticket.change_fee_per_passenger]
    for o, a in zip(case.offers, case.assessments, strict=True):
        in_facts += [o.price, a.breakdown.counted_net_saving, a.breakdown.threshold]
    pairs = {(m.amount, m.currency) for m in money} | {(m.quantized().amount, m.currency) for m in in_facts}
    return AllowedNumbers(money=frozenset(pairs), plain=frozenset(plain), tokens=tuple(tokens))


def allowed_for_recommendation(rec) -> AllowedNumbers:
    """The same allow-list for a finished recommendation (used to check template rationales)."""
    money, plain, tokens = [], set(), []
    for a in rec.candidates:
        tokens.append(a.offer_id)
        if a.breakdown is not None:
            money += _breakdown_money(a.breakdown)
            if a.breakdown.fx is not None:
                plain.add(a.breakdown.fx.rate)
                tokens.append(a.breakdown.fx.source)
    pairs = {(m.amount, m.currency) for m in money}
    for issue in rec.data_issues:
        pairs |= _money_in(issue.detail)
        plain |= numbers_in(issue.detail)
    if rec.error:
        plain |= numbers_in(rec.error)
    return AllowedNumbers(money=frozenset(pairs), plain=frozenset(plain), tokens=tuple(tokens))


def check_rationale(text: str, allowed: AllowedNumbers) -> str | None:
    """None if every number in `text` is accounted for; otherwise a short reason. Catches invented amounts, a wrong
    currency or sign, percentages and numbers in words. It can't tell which real amount a sentence is about; that's
    why every structured field is code-built and the rationale is prefixed with the code's own summary."""
    if "%" in text:
        return "percentages are not allowed"
    if _NUMBER_WORDS.search(text):
        return "numbers written in words are not allowed"
    stripped = text
    for token in sorted(set(allowed.tokens), key=len, reverse=True):
        stripped = stripped.replace(token, " ")
    for match in _MONEY.finditer(stripped):
        amount, currency = match.group("a") or match.group("b"), match.group("c1") or match.group("c2")
        if (Decimal(amount.replace(",", "")), currency) not in allowed.money:
            return f"{amount} {currency} doesn't match any amount in the facts"
    remaining = _MONEY.sub(" ", stripped)
    known = allowed.plain | {abs(amount) for amount, _ in allowed.money}
    for number in numbers_in(remaining):
        if number not in known:
            return f"{number} doesn't appear in the facts"
    return None


def parse_answer(args: object) -> AgentAnswer | str:
    try:
        return AgentAnswer.model_validate(args)
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"invalid submission: {'.'.join(str(p) for p in first['loc']) or '<args>'}: {first['msg']}"
