"""Typed, immutable booking and fare records.

Structure and types only: strict ints and bools, no unknown fields, no silent coercion (D-26). Rules that
relate fields to each other (totals, currencies, dates) live in `loader.py`. Segment and offer times are local
times without an offset, exactly as in the data; the snapshot capture time must carry a timezone.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, StrictBool, StrictInt
from pydantic.alias_generators import to_camel

from rebooking_copilot.money import Money

Airport = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Carrier = Annotated[str, Field(pattern=r"^[A-Z0-9]{2}$")]
FlightNumber = Annotated[str, Field(pattern=r"^[A-Z0-9]{2}[0-9]{1,4}[A-Z]?$")]
FareBasis = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{1,15}$")]
Count = Annotated[StrictInt, Field(ge=0)]


class Cabin(StrEnum):
    BASIC_ECONOMY = "BASIC_ECONOMY"
    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Record(BaseModel):
    """Fixture field names are camelCase; Python attributes are snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, frozen=True, extra="forbid")


class Segment(Record):
    origin: Airport
    destination: Airport
    departure: NaiveDatetime
    arrival: NaiveDatetime
    carrier: Carrier
    flight_number: FlightNumber
    stops: Count
    cabin: Cabin
    fare_basis: FareBasis


class Ticket(Record):
    price_per_passenger: Money
    total_paid: Money
    cabin: Cabin
    refundable: StrictBool
    change_fee_per_passenger: Money
    baggage_included_pieces: Count


class Pnr(Record):
    pnr: Annotated[str, Field(pattern=r"^[A-Z0-9]{6}$")]
    passengers: Annotated[StrictInt, Field(ge=1)]
    itinerary: Annotated[tuple[Segment, ...], Field(min_length=1)]
    ticket: Ticket


class Route(Record):
    origin: Airport
    destination: Airport
    departure_date: date


class Offer(Record):
    offer_id: Annotated[str, Field(min_length=1)]
    route: Route
    carrier: Carrier
    flight_number: FlightNumber
    departure: NaiveDatetime
    arrival: NaiveDatetime
    stops: Count
    cabin: Cabin
    fare_basis: FareBasis
    price: Money
    refundable: StrictBool
    change_fee_per_passenger: Money
    baggage_included_pieces: Count
    seats_available: Count
