"""Load the fixtures into typed records.

Each bad record is rejected on its own with a reason code and never coerced (D-00c, D-26), so every input
booking is accounted for exactly once: accepted, or rejected (later reported as NEEDS_REVIEW). Only an input that
is unusable as a whole (unreadable JSON, missing top-level keys, no timezone-aware capture time) raises `LoaderError`.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, TypeAdapter, ValidationError

from rebooking_copilot.models import Offer, Pnr


class IssueCode(StrEnum):
    DATA_INVALID = "DATA_INVALID"  # wrong type, missing or unknown field, value out of range
    DATA_INCONSISTENT = "DATA_INCONSISTENT"  # fields valid on their own but contradicting each other
    UNSUPPORTED_ITINERARY = "UNSUPPORTED_ITINERARY"  # valid, but outside what v1 can evaluate safely


@dataclass(frozen=True)
class Issue:
    code: IssueCode
    detail: str


@dataclass(frozen=True)
class RejectedPnr:
    index: int
    pnr: str | None
    issues: list[Issue]


@dataclass(frozen=True)
class PnrLoad:
    pnrs: list[Pnr]
    rejected: list[RejectedPnr]


@dataclass(frozen=True)
class RejectedOffer:
    index: int
    offer_id: str | None
    issues: list[Issue]


@dataclass(frozen=True)
class FareSnapshot:
    captured_at: datetime
    offers: list[Offer]
    rejected: list[RejectedOffer]


class LoaderError(Exception):
    """The input as a whole is unusable."""


_CAPTURED_AT = TypeAdapter(AwareDatetime)


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
    accepted: list[Pnr] = []
    rejected: list[RejectedPnr] = []
    for index, record in enumerate(records):
        pnr, issues = _validate(Pnr, record)
        if pnr is not None:
            issues = pnr_issues(pnr)
        if issues:
            rejected.append(RejectedPnr(index, pnr.pnr if pnr else _str_field(record, "pnr"), issues))
        else:
            accepted.append(pnr)
    return PnrLoad(accepted, rejected)


def parse_fare_snapshot(data: dict) -> FareSnapshot:
    try:
        captured_at = _CAPTURED_AT.validate_python(data.get("capturedAt"))
    except ValidationError as exc:
        raise LoaderError(f"capturedAt must be a timezone-aware timestamp: {exc.errors()[0]['msg']}") from exc
    accepted: list[Offer] = []
    rejected: list[RejectedOffer] = []
    for index, record in enumerate(_record_list(data, "offers")):
        offer, issues = _validate(Offer, record)
        if offer is not None:
            issues = offer_issues(offer)
        if issues:
            rejected.append(RejectedOffer(index, offer.offer_id if offer else _str_field(record, "offerId"), issues))
        else:
            accepted.append(offer)
    return FareSnapshot(captured_at, accepted, rejected)


def pnr_issues(pnr: Pnr) -> list[Issue]:
    """Data-quality rules across fields of a structurally valid booking."""
    issues: list[Issue] = []
    ticket = pnr.ticket
    if len(pnr.itinerary) != 1:
        issues.append(Issue(IssueCode.UNSUPPORTED_ITINERARY, f"v1 evaluates single-segment tickets only; got {len(pnr.itinerary)} segments"))
    amounts = (ticket.price_per_passenger, ticket.total_paid, ticket.change_fee_per_passenger)
    if any(m.amount < 0 for m in amounts):
        issues.append(Issue(IssueCode.DATA_INVALID, "ticket amounts must not be negative"))
    currencies = sorted({m.currency for m in amounts})
    if len(currencies) > 1:
        issues.append(Issue(IssueCode.DATA_INCONSISTENT, f"ticket amounts in several currencies: {', '.join(currencies)}"))
    elif ticket.price_per_passenger * pnr.passengers != ticket.total_paid:
        issues.append(
            Issue(
                IssueCode.DATA_INCONSISTENT,
                f"totalPaid {ticket.total_paid} ≠ pricePerPassenger {ticket.price_per_passenger} × {pnr.passengers} passengers",
            )
        )
    if any(segment.cabin != ticket.cabin for segment in pnr.itinerary):
        issues.append(Issue(IssueCode.DATA_INCONSISTENT, "segment cabin differs from ticket cabin"))
    return issues


def offer_issues(offer: Offer) -> list[Issue]:
    """Data-quality rules across fields of a structurally valid offer."""
    issues: list[Issue] = []
    if offer.price.amount < 0 or offer.change_fee_per_passenger.amount < 0:
        issues.append(Issue(IssueCode.DATA_INVALID, "offer amounts must not be negative"))
    if offer.price.currency != offer.change_fee_per_passenger.currency:
        issues.append(Issue(IssueCode.DATA_INCONSISTENT, "price and change fee are in different currencies"))
    if offer.route.departure_date != offer.departure.date():
        issues.append(Issue(IssueCode.DATA_INCONSISTENT, f"route date {offer.route.departure_date} ≠ departure {offer.departure.date()}"))
    return issues


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
        return None, [Issue(IssueCode.DATA_INVALID, detail)]


def _str_field(record: object, key: str) -> str | None:
    value = record.get(key) if isinstance(record, dict) else None
    return value if isinstance(value, str) else None
