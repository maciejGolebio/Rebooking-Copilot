"""Deterministic decision engine (stub mode): one recommendation per input booking.

Pipeline per booking: find candidates → assess each (policy.py) → seat ledger across bookings → choose → action,
confidence, fingerprint. The agent (Claude mode, /slice reasoner) will plug in at the "choose" step; this module is
the deterministic path and the fallback (ADR-0007).

Rules:
- Rejected bookings (loader) → NEEDS_REVIEW, reasons = their issue codes, confidence LOW, no candidates (D-00c).
- No candidates → DO_NOT_REBOOK, NO_CANDIDATES, confidence HIGH.
- Choice (D-29, D-15): the best CLEAN offer first, else the best REVIEW_LEVEL offer. Within a tier: highest counted net
  saving → smallest |schedule shift| → most seats available → offer id (ascending).
- Seat ledger (D-24, D-31): seats are shared by all bookings in one run. Bookings whose preferred offer would end in
  REBOOK are served before those that would end in NEEDS_REVIEW; within each group by the counted net saving of the
  offer the booking would pick (descending; mixed currencies compared in the offer's currency via the inverse of the
  booking's own FX quote, ranking only), then input index. An offer whose remaining seats < passengers is marked
  INELIGIBLE with SEAT_CONTENTION for that booking, and the booking falls through to its next eligible offer.
- Action for the chosen offer:
    CLEAN + settlement CREDIT + cash_only → NEEDS_REVIEW, SAVING_AS_CREDIT (D-10)
    CLEAN otherwise                       → REBOOK (+ FX_CONVERTED if FX was used; + SAVING_AS_CREDIT if credit was counted)
    REVIEW_LEVEL                          → NEEDS_REVIEW with its review-level reasons (D-18: stub never approves these)
  No eligible offer: NEEDS_REVIEW if any candidate had CURRENCY_MISMATCH_NO_FX (could not evaluate), else DO_NOT_REBOOK
  with every candidate's reasons (deduplicated, in first-seen order).
- Confidence (D-28): REBOOK starts HIGH and drops one band for each of FX use, counted net < margin multiple ×
  threshold, snapshot age (as_of − captured_at) > reshop interval. NEEDS_REVIEW → LOW. DO_NOT_REBOOK → HIGH if
  every candidate has net ≤ 0 or a non-money hard block (FEWER_BAGS, SCHEDULE_OUTSIDE_WINDOW, ARRIVES_LATER_DAY,
  INSUFFICIENT_SEATS), else MEDIUM.
- as_of defaults to the snapshot's captured_at (D-18); expires_at = as_of + reshop interval (D-24).
- fingerprint (D-32): sha256 hex of canonical JSON of the booking, its candidate offers, rejected offers on its route,
  the policy, the FX quotes used, as_of, captured_at, the engine version and the reasoner id ("stub"). It covers the
  booking's own inputs only: seat contention with other bookings in the run can change the final recommendation under
  the same fingerprint. The whole run is deterministic.
- Robustness (D-35): an offer on the booking's route that the loader rejected means the picture is incomplete →
  OFFER_DATA_REJECTED: a REBOOK drops one confidence band, a DO_NOT_REBOOK becomes NEEDS_REVIEW. An unexpected error
  while evaluating one booking → NEEDS_REVIEW with EVALUATION_ERROR for that booking only; the run continues.
  `as_of` must be timezone-aware and not earlier than captured_at (a caller error, raised as ValueError).
- Claude mode (`reasoner=`, D-19/D-21): after the ledger, bookings whose seat-feasible eligible set has a review-level
  offer or two or more offers go to the agent. Its answer is re-validated here (D-07, D-16, D-22, D-25): the offer
  must be in that set, REBOOK must pass the settlement gate, every number in the rationale must appear in what the
  model saw; a review-level REBOOK is capped at MEDIUM and the agent's ceiling can only lower confidence; declining
  a clean saving escalates to NEEDS_REVIEW. Anything else falls back to the deterministic recommendation, with the
  reason recorded. Determinism is claimed for stub mode only (D-23).
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime

from rebooking_copilot import __version__
from rebooking_copilot.base import OutputModel
from rebooking_copilot.fx import FxProvider, MockFxProvider
from rebooking_copilot.loader import FareSnapshot, Issue, PnrLoad, RejectedOffer, RejectedPnr
from rebooking_copilot.models import Offer, Pnr
from rebooking_copilot.money import Money, in_money_context, money_context
from rebooking_copilot.outcome import BANDS, Action, Confidence, lowest
from rebooking_copilot.policy import (
    DEFAULT_POLICY, REVIEW_LEVEL_REASONS, Assessment, Breakdown, PolicyConfig, Reason, RuleResult, Settlement,
    SettlementPolicy, Tier, assess, find_candidates, ordered,
)
from rebooking_copilot.rationale import explain
from rebooking_copilot.reasoning import AgentCase, AgentDecision, AgentRun, Reasoner, is_faithful, needs_agent

REASONER_ID = "stub"
__all__ = ["Action", "Confidence", "Recommendation", "REASONER_ID", "evaluate"]


class Recommendation(OutputModel):
    index: int  # position of the booking in the input file
    pnr: str | None
    action: Action
    chosen_offer_id: str | None
    estimated_net_saving: Money | None  # the chosen offer's counted net saving
    breakdown: Breakdown | None  # the chosen offer's breakdown
    confidence: Confidence
    reasons: tuple[Reason, ...]
    alternatives: tuple[str, ...]  # other eligible offer ids, best first
    candidates: tuple[Assessment, ...]
    data_issues: tuple[Issue, ...]
    reasoner: str
    policy_version: str
    as_of: AwareDatetime
    expires_at: AwareDatetime
    fingerprint: str
    error: str | None = None  # only for EVALUATION_ERROR
    rationale: str = ""  # for the human agent: a template (stub) or the agent's text (Claude mode)
    prompt_version: str | None = None  # Claude mode only
    fallback_reason: str | None = None  # why a routed booking fell back to the deterministic decision
    agent_trace: tuple[str, ...] = ()  # tool calls of the agent run, in order


NON_MONEY_BLOCKS = frozenset({Reason.FEWER_BAGS, Reason.SCHEDULE_OUTSIDE_WINDOW, Reason.ARRIVES_LATER_DAY, Reason.INSUFFICIENT_SEATS, Reason.DEPARTS_TOO_SOON})


@in_money_context
def evaluate(
    bookings: PnrLoad,
    snapshot: FareSnapshot,
    *,
    policy: PolicyConfig = DEFAULT_POLICY,
    fx: FxProvider | None = None,
    as_of: datetime | None = None,
    reasoner: Reasoner | None = None,
) -> tuple[Recommendation, ...]:
    """One recommendation per input booking (accepted and rejected), ordered by input index.

    `fx` defaults to MockFxProvider(); `as_of` defaults to snapshot.captured_at; `reasoner=None` is stub mode.
    """
    fx = MockFxProvider() if fx is None else fx
    as_of = snapshot.captured_at if as_of is None else as_of
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if as_of < snapshot.captured_at:
        raise ValueError(f"as_of {as_of.isoformat()} is earlier than the snapshot capture time {snapshot.captured_at.isoformat()}")
    stale = as_of - snapshot.captured_at > policy.reshop_interval
    context = dict(policy=policy, as_of=as_of, expires_at=as_of + policy.reshop_interval, captured_at=snapshot.captured_at)

    total = len(bookings.pnrs) + len(bookings.rejected)
    rejected_indexes = {r.index for r in bookings.rejected}
    accepted_indexes = [i for i in range(total) if i not in rejected_indexes]

    recommendations: dict[int, Recommendation] = {}
    cases: dict[int, tuple[Pnr, tuple[Offer, ...], list[Assessment]]] = {}
    for index, pnr in zip(accepted_indexes, bookings.pnrs, strict=True):
        try:
            offers = find_candidates(pnr, snapshot.offers)
            cases[index] = (pnr, offers, [assess(pnr, o, fx=fx, as_of=as_of, policy=policy) for o in offers])
        except Exception as exc:  # abstain for this booking only (D-00c, D-35)
            recommendations[index] = _errored(index, pnr.pnr, exc, **context)

    chosen, contended = _allocate_seats(cases, policy)

    final: dict[int, tuple[Pnr, tuple[Offer, ...], list[Assessment], tuple[RejectedOffer, ...]]] = {}
    for index, (pnr, offers, assessments) in cases.items():
        try:
            assessments = [_mark_contended(a) if a.offer_id in contended[index] else a for a in assessments]
            lost = _lost_offers(pnr, snapshot.rejected)
            recommendations[index] = _recommend(index, pnr, offers, assessments, chosen[index], lost, stale=stale, **context)
            final[index] = (pnr, offers, assessments, lost)
        except Exception as exc:
            recommendations[index] = _errored(index, pnr.pnr, exc, **context)
    for rejected in bookings.rejected:
        recommendations[rejected.index] = _rejected(rejected, **context)
    recommendations = {i: r.model_copy(update={"rationale": explain(r)}) for i, r in recommendations.items()}
    if reasoner is not None:
        _agent_pass(recommendations, final, chosen, reasoner, stale=stale, **context)
    return tuple(recommendations[i] for i in range(total))


# --- choice and seat ledger -----------------------------------------------------------------------------------------

def _ranked(assessments: list[Assessment]) -> list[Assessment]:
    """Eligible offers, best first: CLEAN before REVIEW_LEVEL (D-29), then D-15 within the tier."""
    eligible = [a for a in assessments if a.tier is not Tier.INELIGIBLE]
    return sorted(
        eligible,
        key=lambda a: (
            a.tier is not Tier.CLEAN,
            -a.breakdown.counted_net_saving.amount,
            abs(a.schedule_shift_minutes),
            -a.seats_available,
            a.offer_id,
        ),
    )


def _credit_blocked(a: Assessment, policy: PolicyConfig) -> bool:
    """D-10/D-30: under cash_only a credit saving is reported but can never become REBOOK."""
    return a.breakdown.settlement is Settlement.CREDIT and policy.settlement_policy is SettlementPolicy.CASH_ONLY


def _would_rebook(a: Assessment, policy: PolicyConfig) -> bool:
    return a.tier is Tier.CLEAN and not _credit_blocked(a, policy)


def _saving_in_offer_currency(a: Assessment) -> Decimal:
    """Ranking only (D-31): the counted saving in the offer's currency, via the inverse of the booking's own quote."""
    counted = a.breakdown.counted_net_saving.amount
    if a.breakdown.fx is None:
        return counted
    with money_context():
        return counted / a.breakdown.fx.rate


def _allocate_seats(cases, policy: PolicyConfig) -> tuple[dict[int, Assessment | None], dict[int, set[str]]]:
    """Deferred acceptance over the run's shared seats (D-24, D-31).

    Each booking proposes to its eligible offers in preference order. Each offer keeps the proposers that fit its
    seats, by priority: REBOOK-bound first, then the counted saving in the offer's currency (descending), then input
    index. A displaced or rejected booking proposes to its next offer. Only proposers for the same offer are ever
    compared, so amounts in different currencies are never mixed.
    """
    preferences = {i: _ranked(assessments) for i, (_, _, assessments) in cases.items()}
    passengers = {i: pnr.passengers for i, (pnr, _, _) in cases.items()}
    next_proposal = dict.fromkeys(preferences, 0)
    seats: dict[str, int] = {}
    held: dict[str, list[tuple[tuple, int, Assessment]]] = {}
    contended: dict[int, set[str]] = {i: set() for i in preferences}
    free = sorted(i for i, prefs in preferences.items() if prefs)
    while free:
        i = free.pop(0)
        if next_proposal[i] >= len(preferences[i]):
            continue
        a = preferences[i][next_proposal[i]]
        next_proposal[i] += 1
        seats.setdefault(a.offer_id, a.seats_available)
        priority = (not _would_rebook(a, policy), -_saving_in_offer_currency(a), i)
        entries = sorted([*held.get(a.offer_id, []), (priority, i, a)], key=lambda e: e[0])
        kept, used = [], 0
        for entry in entries:
            if used + passengers[entry[1]] <= seats[a.offer_id]:
                kept.append(entry)
                used += passengers[entry[1]]
            else:
                contended[entry[1]].add(a.offer_id)
                free.append(entry[1])
        held[a.offer_id] = kept
        free.sort()
    chosen: dict[int, Assessment | None] = dict.fromkeys(preferences)
    for entries in held.values():
        for _, i, a in entries:
            chosen[i] = a
    _fill_freed_seats(preferences, passengers, seats, held, chosen, contended, policy)
    return chosen, contended


def _fill_freed_seats(preferences, passengers, seats, held, chosen, contended, policy: PolicyConfig) -> None:
    """A displacement can free seats on an offer that earlier rejected a smaller booking (D-35). Offer each free seat
    block to the highest-priority booking that fits and prefers that offer to its current one; repeat until stable.
    Each move strictly improves one booking's assignment, so this terminates; holders are never displaced here."""
    rank = {i: {a.offer_id: k for k, a in enumerate(prefs)} for i, prefs in preferences.items()}
    moved = True
    while moved:
        moved = False
        for offer_id in sorted(seats):
            free_seats = seats[offer_id] - sum(passengers[i] for _, i, _ in held.get(offer_id, []))
            movers = []
            for i, prefs in preferences.items():
                if offer_id not in rank[i] or passengers[i] > free_seats:
                    continue
                current = chosen[i]
                if current is not None and rank[i][current.offer_id] <= rank[i][offer_id]:
                    continue
                a = prefs[rank[i][offer_id]]
                movers.append(((not _would_rebook(a, policy), -_saving_in_offer_currency(a), i), i, a))
            if not movers:
                continue
            priority, i, a = min(movers, key=lambda e: e[0])
            if chosen[i] is not None:
                held[chosen[i].offer_id] = [e for e in held[chosen[i].offer_id] if e[1] != i]
            held.setdefault(offer_id, []).append((priority, i, a))
            chosen[i] = a
            contended[i].discard(offer_id)
            moved = True
            break


def _mark_contended(a: Assessment) -> Assessment:
    return a.model_copy(
        update={
            "tier": Tier.INELIGIBLE,
            "reasons": ordered((*a.reasons, Reason.SEAT_CONTENTION)),
            "rule_trace": (*a.rule_trace, RuleResult(rule="seat_ledger", passed=False, detail="seats taken by higher-priority bookings in this run")),
        }
    )


# --- recommendations ------------------------------------------------------------------------------------------------

def _lost_offers(pnr: Pnr, rejected: tuple[RejectedOffer, ...]) -> tuple[RejectedOffer, ...]:
    segment = pnr.itinerary[0]
    route = (segment.origin, segment.destination, segment.departure.date().isoformat())
    return tuple(r for r in rejected if (r.origin, r.destination, r.departure_date) == route)


def _recommend(index, pnr: Pnr, offers, assessments: list[Assessment], chosen: Assessment | None, lost=(), **context) -> Recommendation:
    rec = _decide(index, pnr, offers, assessments, chosen, lost, **context)
    if not lost:
        return rec
    return _with_lost(rec)


def _with_lost(rec: Recommendation) -> Recommendation:
    """D-35: a rejected offer on the route means the picture is incomplete."""
    reasons = ordered((*rec.reasons, Reason.OFFER_DATA_REJECTED))
    if rec.action is Action.REBOOK:
        return rec.model_copy(update={"reasons": reasons, "confidence": BANDS[min(BANDS.index(rec.confidence) + 1, 2)]})
    return rec.model_copy(update={"action": Action.NEEDS_REVIEW, "confidence": Confidence.LOW, "reasons": reasons})


def _decide(index, pnr: Pnr, offers, assessments: list[Assessment], chosen: Assessment | None, lost, *, stale: bool, policy, as_of, expires_at, captured_at) -> Recommendation:
    fingerprint = _fingerprint(
        booking=pnr.model_dump(mode="json"),
        candidates=[o.model_dump(mode="json") for o in offers],
        rejected_offers=[r.model_dump(mode="json") for r in lost],
        fx=[a.breakdown.fx.model_dump(mode="json") for a in assessments if a.breakdown is not None and a.breakdown.fx is not None],
        policy=policy, as_of=as_of, captured_at=captured_at,
    )
    common = dict(
        index=index, pnr=pnr.pnr, candidates=tuple(assessments), data_issues=(), reasoner=REASONER_ID,
        policy_version=policy.version, as_of=as_of, expires_at=expires_at, fingerprint=fingerprint,
    )
    if not offers:
        return Recommendation(
            action=Action.DO_NOT_REBOOK, chosen_offer_id=None, estimated_net_saving=None, breakdown=None,
            confidence=Confidence.HIGH, reasons=(Reason.NO_CANDIDATES,), alternatives=(), **common,
        )
    if chosen is None:
        reasons = tuple(dict.fromkeys(r for a in assessments for r in a.reasons))  # first seen, candidates in input order
        if Reason.CURRENCY_MISMATCH_NO_FX in reasons:
            action, confidence = Action.NEEDS_REVIEW, Confidence.LOW
        else:
            settled = all(a.breakdown is None or a.breakdown.net_saving.amount <= 0 or set(a.reasons) & NON_MONEY_BLOCKS for a in assessments)
            action, confidence = Action.DO_NOT_REBOOK, Confidence.HIGH if settled else Confidence.MEDIUM
        return Recommendation(
            action=action, chosen_offer_id=None, estimated_net_saving=None, breakdown=None, confidence=confidence,
            reasons=reasons, alternatives=(), **common,
        )

    bd = chosen.breakdown
    alternatives = tuple(a.offer_id for a in _ranked(assessments) if a.offer_id != chosen.offer_id)
    notes = [Reason.FX_CONVERTED] if bd.fx is not None else []
    if chosen.tier is Tier.REVIEW_LEVEL:
        action, confidence, reasons = Action.NEEDS_REVIEW, Confidence.LOW, ordered((*chosen.reasons, *notes))
    else:
        if bd.settlement is Settlement.CREDIT:
            notes.append(Reason.SAVING_AS_CREDIT)
        if _would_rebook(chosen, policy):
            drops = (bd.fx is not None) + (bd.counted_net_saving.amount < policy.confidence_margin_multiple * bd.threshold.amount) + stale
            action, confidence = Action.REBOOK, BANDS[min(drops, 2)]
        else:
            action, confidence = Action.NEEDS_REVIEW, Confidence.LOW
        reasons = ordered(notes)
    return Recommendation(
        action=action, chosen_offer_id=chosen.offer_id, estimated_net_saving=bd.counted_net_saving, breakdown=bd,
        confidence=confidence, reasons=reasons, alternatives=alternatives, **common,
    )


def _rejected(rejected: RejectedPnr, *, policy, as_of, expires_at, captured_at) -> Recommendation:
    return Recommendation(
        index=rejected.index, pnr=rejected.pnr, action=Action.NEEDS_REVIEW, chosen_offer_id=None, estimated_net_saving=None,
        breakdown=None, confidence=Confidence.LOW, reasons=tuple(dict.fromkeys(Reason(i.code.value) for i in rejected.issues)),
        alternatives=(), candidates=(), data_issues=rejected.issues, reasoner=REASONER_ID, policy_version=policy.version,
        as_of=as_of, expires_at=expires_at,
        fingerprint=_fingerprint(rejected=rejected.model_dump(mode="json"), policy=policy, as_of=as_of, captured_at=captured_at),
    )


def _errored(index: int, locator: str | None, exc: Exception, *, policy, as_of, expires_at, captured_at) -> Recommendation:
    return Recommendation(
        index=index, pnr=locator, action=Action.NEEDS_REVIEW, chosen_offer_id=None, estimated_net_saving=None, breakdown=None,
        confidence=Confidence.LOW, reasons=(Reason.EVALUATION_ERROR,), alternatives=(), candidates=(), data_issues=(),
        reasoner=REASONER_ID, policy_version=policy.version, as_of=as_of, expires_at=expires_at,
        fingerprint=_fingerprint(error=f"{type(exc).__name__}", pnr=locator, policy=policy, as_of=as_of, captured_at=captured_at),
        error=f"{type(exc).__name__}: {exc}",
    )


def _fingerprint(*, policy: PolicyConfig, as_of: datetime, captured_at: datetime, reasoner: str = REASONER_ID, **parts) -> str:
    """D-32: the booking's own inputs only (booking, candidate and rejected offers, FX quotes used, policy, clocks, engine)."""
    payload = {
        **parts, "policy": policy.model_dump(mode="json"), "as_of": as_of.isoformat(), "captured_at": captured_at.isoformat(),
        "engine": __version__, "reasoner": reasoner,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --- Claude mode: routing and the validator (D-07, D-16, D-21, D-22, D-25) -----------------------------------------

def _agent_pass(recommendations, final, chosen, reasoner: Reasoner, *, stale: bool, policy, as_of, expires_at, captured_at) -> None:
    """Route eligible bookings to the agent, in input order, over the seats the ledger left (no overselling)."""
    held_by = {i: a.offer_id for i, a in chosen.items() if a is not None}
    seats: dict[str, int] = {}
    used: dict[str, int] = {}
    for i, (pnr, _, assessments, _) in final.items():
        for a in assessments:
            seats.setdefault(a.offer_id, a.seats_available)
        if i in held_by:
            used[held_by[i]] = used.get(held_by[i], 0) + pnr.passengers

    for index in sorted(final):
        pnr, offers, assessments, lost = final[index]
        held = held_by.get(index)
        eligible = _ranked(assessments)
        feasible = [a for a in eligible if a.offer_id == held or seats[a.offer_id] - used.get(a.offer_id, 0) >= pnr.passengers]
        if not needs_agent(feasible):
            continue
        by_id = {o.offer_id: o for o in offers}
        feasible_ids = {a.offer_id for a in feasible}
        case = AgentCase(
            pnr=pnr, offers=tuple(by_id[a.offer_id] for a in feasible), assessments=tuple(feasible),
            seat_blocked=frozenset(a.offer_id for a in eligible if a.offer_id not in feasible_ids), policy=policy,
        )
        try:
            run = reasoner.run(case)
        except Exception as exc:  # a reasoner must never take the run down
            run = AgentRun(failure=f"reasoner error: {type(exc).__name__}: {exc}")
        rec = _apply_agent(
            recommendations[index], run, case, reasoner, offers=offers, assessments=assessments, lost=lost,
            stale=stale, policy=policy, as_of=as_of, captured_at=captured_at,
        )
        if rec.action is Action.REBOOK and rec.chosen_offer_id != held:
            used[rec.chosen_offer_id] = used.get(rec.chosen_offer_id, 0) + pnr.passengers
            if held is not None:
                used[held] -= pnr.passengers
        recommendations[index] = rec


def _apply_agent(rec: Recommendation, run: AgentRun, case: AgentCase, reasoner: Reasoner, *, offers, assessments, lost,
                 stale: bool, policy: PolicyConfig, as_of, captured_at) -> Recommendation:
    """Re-validate the agent's answer against the code-built set; any violation falls back to `rec`."""

    def fallback(reason: str) -> Recommendation:
        return rec.model_copy(update={"fallback_reason": reason, "agent_trace": run.trace})

    if run.failure is not None or run.answer is None:
        return fallback(run.failure or "no answer")
    answer = run.answer
    feasible = {a.offer_id: a for a in case.assessments}
    chosen_id = answer.chosen_offer_id
    if chosen_id is not None and chosen_id not in feasible:
        if chosen_id in case.seat_blocked:
            return fallback(f"no seats left on {chosen_id} after other bookings in this run")
        return fallback(f"{chosen_id} is not in the eligible set")
    if answer.decision is AgentDecision.REBOOK and chosen_id is None:
        return fallback("REBOOK needs an offer from the eligible set")
    chosen = feasible.get(chosen_id)
    if answer.decision is AgentDecision.REBOOK and _credit_blocked(chosen, policy):
        return fallback(f"policy forbids REBOOK on {chosen_id}: the saving would come back as credit under cash_only")
    if not is_faithful(answer.rationale, run.seen_text):
        return fallback("unfaithful rationale: it states numbers that are not in the facts or tool results")

    ranked = list(case.assessments)  # best first
    best_clean = next((a for a in ranked if _would_rebook(a, policy)), None)
    rationale = answer.rationale
    if answer.decision is AgentDecision.REBOOK:
        bd = chosen.breakdown
        drops = (bd.fx is not None) + (bd.counted_net_saving.amount < policy.confidence_margin_multiple * bd.threshold.amount) + stale
        confidence = BANDS[min(drops, 2)]
        if chosen.tier is Tier.REVIEW_LEVEL:
            confidence = lowest(confidence, Confidence.MEDIUM)  # D-16
        confidence = lowest(confidence, answer.confidence_ceiling)  # D-17: the model can only lower it
        notes = [Reason.FX_CONVERTED] if bd.fx is not None else []
        if bd.settlement is Settlement.CREDIT:
            notes.append(Reason.SAVING_AS_CREDIT)
        reasons = ordered((*(r for r in chosen.reasons if r in REVIEW_LEVEL_REASONS), *notes))
        update = dict(action=Action.REBOOK, chosen_offer_id=chosen.offer_id, estimated_net_saving=bd.counted_net_saving,
                      breakdown=bd, confidence=confidence, reasons=reasons)
    elif best_clean is not None:  # D-22: declining a clean saving the policy approves → a human decides
        bd = best_clean.breakdown
        update = dict(action=Action.NEEDS_REVIEW, chosen_offer_id=best_clean.offer_id, estimated_net_saving=bd.counted_net_saving,
                      breakdown=bd, confidence=Confidence.LOW, reasons=ordered((*best_clean.reasons, Reason.LLM_DISAGREES_WITH_POLICY)))
    elif answer.decision is AgentDecision.NEEDS_REVIEW and chosen is not None:
        bd = chosen.breakdown
        notes = [Reason.FX_CONVERTED] if bd.fx is not None else []
        update = dict(action=Action.NEEDS_REVIEW, chosen_offer_id=chosen.offer_id, estimated_net_saving=bd.counted_net_saving,
                      breakdown=bd, confidence=Confidence.LOW, reasons=ordered((*chosen.reasons, *notes)))
    else:
        reasons = tuple(dict.fromkeys(r for a in ranked for r in a.reasons))
        if answer.decision is AgentDecision.NEEDS_REVIEW:
            action, confidence = Action.NEEDS_REVIEW, Confidence.LOW
        else:
            settled = all(a.breakdown.net_saving.amount <= 0 or set(a.reasons) & NON_MONEY_BLOCKS for a in ranked)
            action, confidence = Action.DO_NOT_REBOOK, Confidence.HIGH if settled else Confidence.MEDIUM
        update = dict(action=action, chosen_offer_id=None, estimated_net_saving=None, breakdown=None, confidence=confidence, reasons=reasons)

    alternatives = tuple(a.offer_id for a in ranked if update["chosen_offer_id"] is not None and a.offer_id != update["chosen_offer_id"])
    fingerprint = _fingerprint(
        booking=case.pnr.model_dump(mode="json"),
        candidates=[o.model_dump(mode="json") for o in offers],
        rejected_offers=[r.model_dump(mode="json") for r in lost],
        fx=[a.breakdown.fx.model_dump(mode="json") for a in assessments if a.breakdown is not None and a.breakdown.fx is not None],
        prompt=reasoner.prompt_version, policy=policy, as_of=as_of, captured_at=captured_at, reasoner=reasoner.id,
    )
    new = rec.model_copy(update={
        **update, "alternatives": alternatives, "reasoner": reasoner.id, "prompt_version": reasoner.prompt_version,
        "agent_trace": run.trace, "fallback_reason": None, "fingerprint": fingerprint,
    })
    if Reason.LLM_DISAGREES_WITH_POLICY in new.reasons:
        rationale = f"{explain(new)} The agent's view: {answer.rationale}"
    if lost:
        new = _with_lost(new)
    return new.model_copy(update={"rationale": rationale})
