"""Load the fixtures into typed records.

Each bad record is rejected on its own with a reason code and never coerced (D-00c, D-26), so every input
booking is accounted for exactly once: accepted, or rejected (later reported as NEEDS_REVIEW). Only an input that
is unusable as a whole (unreadable JSON, missing top-level keys, no timezone-aware capture time) raises `LoaderError`.
"""

import json
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from rebooking_copilot.models import Offer, Pnr


class IssueCode(StrEnum):
    DATA_INVALID = "DATA_INVALID"  # wrong type, missing or unknown field, value out of range
    DATA_INCONSISTENT = "DATA_INCONSISTENT"  # fields valid on their own but contradicting each other
    UNSUPPORTED_ITINERARY = "UNSUPPORTED_ITINERARY"  # valid, but outside what v1 can evaluate safely


class Result(BaseModel):
    """Immutable result types; pydantic so they serialise into the output and its JSON Schema (D-05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Issue(Result):
    code: IssueCode
    detail: str


class RejectedPnr(Result):
    index: int
    pnr: str | None
    issues: tuple[Issue, ...]


class PnrLoad(Result):
    pnrs: tuple[Pnr, ...]
    rejected: tuple[RejectedPnr, ...]


class RejectedOffer(Result):
    index: int
    offer_id: str | None
    issues: tuple[Issue, ...]
    # Best-effort route from the raw record, so bookings on that route know an offer was lost (D-35). None if unreadable.
    origin: str | None = None
    destination: str | None = None
    departure_date: str | None = None


class FareSnapshot(Result):
    captured_at: AwareDatetime
    offers: tuple[Offer, ...]
    rejected: tuple[RejectedOffer, ...]


class LoaderError(Exception):
    """The input as a whole is unusable."""


def read_json(path: Path) -> dict:
    """Read a JSON object with every non-integer number parsed as an exact Decimal."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            data = json.load(fh, parse_float=Decimal)
    except (OSError, json.JSONDecodeError) as exc:
        raise LoaderError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LoaderError(f"{path}: expected a JSON object at the top level")
    return data


def load_pnrs(path: Path) -> PnrLoad:
    return parse_pnrs(read_json(path))


def load_fare_snapshot(path: Path) -> FareSnapshot:
    return parse_fare_snapshot(read_json(path))


def parse_pnrs(data: dict) -> PnrLoad:
    records = _record_list(data, "pnrs")
    duplicates = _duplicates(_str_field(r, "pnr") for r in records)
    accepted: list[Pnr] = []
    rejected: list[RejectedPnr] = []
    for index, record in enumerate(records):
        pnr, issues = _validate(Pnr, record)
        if pnr is not None:
            issues = _guarded(pnr_issues, pnr)
        if _str_field(record, "pnr") in duplicates:
            issues = [*issues, Issue(code=IssueCode.DATA_INCONSISTENT, detail="PNR locator appears more than once in the input")]
        if issues:
            rejected.append(RejectedPnr(index=index, pnr=pnr.pnr if pnr else _str_field(record, "pnr"), issues=tuple(issues)))
        else:
            accepted.append(pnr)
    return PnrLoad(pnrs=tuple(accepted), rejected=tuple(rejected))


def parse_fare_snapshot(data: dict) -> FareSnapshot:
    records = _record_list(data, "offers")
    duplicates = _duplicates(_str_field(r, "offerId") for r in records)
    accepted: list[Offer] = []
    rejected: list[RejectedOffer] = []
    for index, record in enumerate(records):
        offer, issues = _validate(Offer, record)
        if offer is not None:
            issues = _guarded(offer_issues, offer)
        if _str_field(record, "offerId") in duplicates:
            issues = [*issues, Issue(code=IssueCode.DATA_INCONSISTENT, detail="offerId appears more than once in the snapshot")]
        if issues:
            route = record.get("route") if isinstance(record, dict) else None
            rejected.append(
                RejectedOffer(
                    index=index,
                    offer_id=offer.offer_id if offer else _str_field(record, "offerId"),
                    issues=tuple(issues),
                    origin=_str_field(route, "origin"),
                    destination=_str_field(route, "destination"),
                    departure_date=_str_field(route, "departureDate"),
                )
            )
        else:
            accepted.append(offer)
    try:
        return FareSnapshot(captured_at=data.get("capturedAt"), offers=tuple(accepted), rejected=tuple(rejected))
    except ValidationError as exc:
        raise LoaderError(f"capturedAt must be a timezone-aware timestamp: {exc.errors()[0]['msg']}") from exc


def pnr_issues(pnr: Pnr) -> list[Issue]:
    """Data-quality rules across fields of a structurally valid booking."""
    issues: list[Issue] = []
    ticket = pnr.ticket
    if len(pnr.itinerary) != 1:
        issues.append(Issue(code=IssueCode.UNSUPPORTED_ITINERARY, detail=f"v1 evaluates single-segment tickets only; got {len(pnr.itinerary)} segments"))
    amounts = (ticket.price_per_passenger, ticket.total_paid, ticket.change_fee_per_passenger)
    if any(m.amount < 0 for m in amounts):
        issues.append(Issue(code=IssueCode.DATA_INVALID, detail="ticket amounts must not be negative"))
    currencies = sorted({m.currency for m in amounts})
    if len(currencies) > 1:
        issues.append(Issue(code=IssueCode.DATA_INCONSISTENT, detail=f"ticket amounts in several currencies: {', '.join(currencies)}"))
    elif ticket.price_per_passenger * pnr.passengers != ticket.total_paid:
        issues.append(
            Issue(
                code=IssueCode.DATA_INCONSISTENT,
                detail=f"totalPaid {ticket.total_paid} ≠ pricePerPassenger {ticket.price_per_passenger} × {pnr.passengers} passengers",
            )
        )
    if any(segment.cabin != ticket.cabin for segment in pnr.itinerary):
        issues.append(Issue(code=IssueCode.DATA_INCONSISTENT, detail="segment cabin differs from ticket cabin"))
    return issues


def offer_issues(offer: Offer) -> list[Issue]:
    """Data-quality rules across fields of a structurally valid offer."""
    issues: list[Issue] = []
    if offer.price.amount <= 0:
        issues.append(Issue(code=IssueCode.DATA_INVALID, detail="offer price must be positive"))
    if offer.change_fee_per_passenger.amount < 0:
        issues.append(Issue(code=IssueCode.DATA_INVALID, detail="offer change fee must not be negative"))
    if offer.price.currency != offer.change_fee_per_passenger.currency:
        issues.append(Issue(code=IssueCode.DATA_INCONSISTENT, detail="price and change fee are in different currencies"))
    if offer.route.departure_date != offer.departure.date():
        issues.append(Issue(code=IssueCode.DATA_INCONSISTENT, detail=f"route date {offer.route.departure_date} ≠ departure {offer.departure.date()}"))
    return issues


def _duplicates(values) -> set[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value is not None:
            (repeated if value in seen else seen).add(value)
    return repeated


def _guarded(check, record) -> list[Issue]:
    """Data-quality checks do arithmetic on input values; if that arithmetic fails, the record is invalid data."""
    try:
        return check(record)
    except ArithmeticError as exc:
        return [Issue(code=IssueCode.DATA_INVALID, detail=f"amounts can't be evaluated: {type(exc).__name__}")]


def _record_list(data: dict, key: str) -> list:
    records = data.get(key)
    if not isinstance(records, list):
        raise LoaderError(f"expected a '{key}' list at the top level")
    return records


def _validate[M: BaseModel](model: type[M], record: object) -> tuple[M | None, list[Issue]]:
    try:
        return model.model_validate(record), []
    except ValidationError as exc:
        detail = "; ".join(f"{'.'.join(str(p) for p in err['loc']) or '<record>'}: {err['msg']}" for err in exc.errors())
        return None, [Issue(code=IssueCode.DATA_INVALID, detail=detail)]


def _str_field(record: object, key: str) -> str | None:
    value = record.get(key) if isinstance(record, dict) else None
    return value if isinstance(value, str) else None
