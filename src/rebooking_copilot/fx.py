"""Currency conversion behind an API-shaped provider (D-12, D-27).

`FxProvider` is the seam for a real FX/treasury API. `MockFxProvider` stands in for it: it returns *executable*
rates (spread already included, as an API quote would), labelled with their source and as-of time. A missing pair
raises `FxUnavailableError`; callers abstain rather than guess (D-00b). No inverse is derived from a quoted pair,
because an executable rate carries its spread in one direction. A quote that doesn't match the request, is stale, or
comes with a provider error is treated the same way (`FxQuoteInvalidError`, D-35).
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Protocol

from pydantic import AwareDatetime, Field

from rebooking_copilot.base import OutputModel

from rebooking_copilot.money import Amount, CurrencyCode, CurrencyMismatchError, Money, money_context

# Illustrative only: ≈ 1.10 USD/EUR mid less ~2% spread, expressed as EUR per 1 USD.
MOCK_RATES: dict[tuple[str, str], Decimal] = {("USD", "EUR"): Decimal("0.9276")}
MOCK_SOURCE = "mock-fx-v1"


class FxQuote(OutputModel):
    """`rate` = units of `to_currency` per 1 unit of `from_currency`."""

    from_currency: CurrencyCode
    to_currency: CurrencyCode
    rate: Annotated[Amount, Field(gt=0)]
    as_of: AwareDatetime
    source: str


class FxUnavailableError(LookupError):
    """No usable rate for the requested pair."""


class FxQuoteInvalidError(FxUnavailableError):
    """The provider answered, but the quote can't be trusted (wrong pair, stale, provider error)."""


class FxProvider(Protocol):
    def quote(self, from_currency: str, to_currency: str, as_of: datetime) -> FxQuote: ...


class MockFxProvider:
    """Static, labelled rates standing in for an FX API. Same currency → rate 1; unknown pair → FxUnavailableError."""

    def __init__(self, rates: Mapping[tuple[str, str], Decimal] | None = None, source: str = MOCK_SOURCE) -> None:
        self._rates = dict(MOCK_RATES if rates is None else rates)
        self._source = source

    def quote(self, from_currency: str, to_currency: str, as_of: datetime) -> FxQuote:
        if from_currency == to_currency:
            rate = Decimal(1)
        else:
            try:
                rate = self._rates[(from_currency, to_currency)]
            except KeyError:
                raise FxUnavailableError(f"no {from_currency}→{to_currency} rate from {self._source}") from None
        return FxQuote(from_currency=from_currency, to_currency=to_currency, rate=rate, as_of=as_of, source=self._source)


def convert(money: Money, quote: FxQuote) -> Money:
    """Exact conversion; `money.currency` must equal `quote.from_currency` (else CurrencyMismatchError)."""
    if money.currency != quote.from_currency:
        raise CurrencyMismatchError(f"cannot convert {money.currency} with a {quote.from_currency}→{quote.to_currency} quote")
    with money_context():
        return Money(amount=money.amount * quote.rate, currency=quote.to_currency)
