"""Currency-tagged exact money (D-00b).

Amounts are `Decimal`; floats are rejected at the boundary. Adding, subtracting or comparing amounts in
different currencies raises `CurrencyMismatchError`. Conversion happens only through an explicit FX provider,
never here. Rounding happens only for presentation (`quantized`, `str`), with ROUND_HALF_EVEN to ISO 4217 minor units.
Arithmetic runs in a fixed local Decimal context (`MONEY_CONTEXT`), so it doesn't depend on the process-wide context, and
amounts are bounded at the boundary so absurd values are rejected as data, not crashes.
"""

import functools
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer, WithJsonSchema

# ISO 4217 minor units for the currencies we accept. An unknown code is a data problem, not something to guess.
MINOR_UNITS: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2, "NZD": 2, "SEK": 2, "NOK": 2, "DKK": 2,
    "PLN": 2, "CZK": 2, "HUF": 2, "MXN": 2, "BRL": 2, "COP": 2, "SGD": 2, "HKD": 2, "CNY": 2, "INR": 2,
    "ZAR": 2, "AED": 2, "JPY": 0, "KRW": 0, "CLP": 0, "ISK": 0, "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3,
}


MONEY_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN, Emax=999_999, Emin=-999_999, traps=[InvalidOperation, DivisionByZero, Overflow])
MAX_ABS_AMOUNT = Decimal(10) ** 12  # far above any ticket in any currency; beyond it the record is invalid data


def money_context():
    """The fixed Decimal context for all money arithmetic."""
    return localcontext(MONEY_CONTEXT)


def in_money_context(fn):
    """Run a whole function under MONEY_CONTEXT, so every Decimal operation in it is independent of the caller's context."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with money_context():
            return fn(*args, **kwargs)

    return wrapper


class CurrencyMismatchError(ValueError):
    """Amounts in different currencies were combined or compared."""


def _exact_decimal(value: object) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ValueError(f"money amounts must be exact (Decimal, int or numeric string), got {type(value).__name__}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal number: {value!r}") from exc
    else:
        raise ValueError(f"unsupported amount type {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("money amounts must be finite")
    if abs(result) > MAX_ABS_AMOUNT:
        raise ValueError(f"money amount out of range (|amount| > {MAX_ABS_AMOUNT:,})")
    return result


def _known_currency(value: object) -> str:
    if not isinstance(value, str) or value not in MINOR_UNITS:
        raise ValueError(f"unknown or malformed ISO 4217 currency code: {value!r}")
    return value


DECIMAL_PATTERN = r"^-?\d+(\.\d+)?$"

# Exact in, exact out: JSON gets fixed-point text (never "5E+1"), and the schema says so.
Amount = Annotated[
    Decimal,
    BeforeValidator(_exact_decimal),
    PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": DECIMAL_PATTERN, "description": "Exact decimal, fixed-point notation"}, mode="serialization"),
]
CurrencyCode = Annotated[str, BeforeValidator(_known_currency)]


class Money(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Amount
    currency: CurrencyCode

    @classmethod
    def zero(cls, currency: str) -> Self:
        return cls(amount=Decimal(0), currency=currency)

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"cannot combine {self.currency} with {other.currency} without an FX rate")

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        with money_context():
            return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        with money_context():
            return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: object) -> "Money":
        if isinstance(factor, bool) or not isinstance(factor, (int, Decimal)):
            raise TypeError("money can only be multiplied by an int or a Decimal")
        with money_context():
            return Money(amount=self.amount * factor, currency=self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(amount=-self.amount, currency=self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount >= other.amount

    def quantized(self) -> "Money":
        """Rounded to the currency's minor units (ROUND_HALF_EVEN). For presentation and settlement only."""
        exponent = Decimal(1).scaleb(-MINOR_UNITS[self.currency])
        with money_context():
            return Money(amount=self.amount.quantize(exponent, rounding=ROUND_HALF_EVEN), currency=self.currency)

    def __str__(self) -> str:
        return f"{self.quantized().amount} {self.currency}"
