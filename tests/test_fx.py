"""FX provider seam and exact conversion (D-12, D-27, D-00b)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from factories import CAPTURED_AT, MOCK_USD_EUR, eur, usd
from rebooking_copilot.fx import MOCK_SOURCE, FxQuote, FxUnavailableError, MockFxProvider, convert
from rebooking_copilot.money import CurrencyMismatchError, Money

AS_OF = CAPTURED_AT


def quote(from_currency: str, to_currency: str, rate: str, source: str = "test") -> FxQuote:
    return FxQuote(from_currency=from_currency, to_currency=to_currency, rate=Decimal(rate), as_of=AS_OF, source=source)


# --- MockFxProvider.quote -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("currency", ["USD", "EUR", "JPY"])
def test_same_currency_quotes_rate_one(currency):
    # D-27: same currency → rate 1, even for a currency the table doesn't mention.
    q = MockFxProvider().quote(currency, currency, AS_OF)
    assert q.rate == Decimal(1)
    assert (q.from_currency, q.to_currency) == (currency, currency)


def test_known_pair_returns_the_executable_mock_rate():
    # D-27: USD→EUR 0.9276 EUR per USD (≈1.10 mid less ~2% spread), source mock-fx-v1.
    q = MockFxProvider().quote("USD", "EUR", AS_OF)
    assert isinstance(q, FxQuote)
    assert (q.from_currency, q.to_currency) == ("USD", "EUR")
    assert q.rate == MOCK_USD_EUR
    assert isinstance(q.rate, Decimal)


def test_quote_carries_source_and_as_of():
    q = MockFxProvider().quote("USD", "EUR", AS_OF)
    assert q.source == MOCK_SOURCE == "mock-fx-v1"
    assert q.as_of == AS_OF


def test_quote_as_of_follows_the_requested_time():
    # The mock table has no timestamps of its own; the injected clock is the only time source (D-18, no wall clock).
    later = AS_OF + timedelta(days=3)
    assert MockFxProvider().quote("USD", "EUR", later).as_of == later
    assert MockFxProvider().quote("EUR", "EUR", later).as_of == later


@pytest.mark.parametrize("pair", [("GBP", "USD"), ("USD", "JPY"), ("EUR", "USD")])
def test_missing_pair_raises_fx_unavailable(pair):
    # D-27: missing pair → FxUnavailableError. EUR→USD is missing too: no inverse is derived from USD→EUR,
    # because an executable rate includes a spread in one direction.
    with pytest.raises(FxUnavailableError):
        MockFxProvider().quote(*pair, AS_OF)


def test_fx_unavailable_is_a_lookup_error():
    assert issubclass(FxUnavailableError, LookupError)


def test_injected_table_replaces_the_default_and_labels_its_source():
    provider = MockFxProvider(rates={("GBP", "USD"): Decimal("1.25")}, source="test-desk")
    q = provider.quote("GBP", "USD", AS_OF)
    assert q.rate == Decimal("1.25")
    assert q.source == "test-desk"
    with pytest.raises(FxUnavailableError):
        provider.quote("USD", "EUR", AS_OF)


def test_empty_table_still_quotes_same_currency():
    provider = MockFxProvider(rates={})
    assert provider.quote("USD", "USD", AS_OF).rate == Decimal(1)
    with pytest.raises(FxUnavailableError):
        provider.quote("USD", "EUR", AS_OF)


# --- convert ------------------------------------------------------------------------------------------------------

def test_convert_is_exact():
    # D-27 consequence: 2100.00 USD × 0.9276 = 1947.96 EUR.
    assert convert(usd("2100.00"), quote("USD", "EUR", "0.9276")) == eur("1947.96")


def test_convert_does_not_round_to_minor_units():
    # Rounding is for presentation only (money.py, D-26): 0.01 USD × 0.9276 = 0.009276 EUR, not 0.01.
    converted = convert(usd("0.01"), quote("USD", "EUR", "0.9276"))
    assert converted.currency == "EUR"
    assert converted.amount == Decimal("0.009276")


def test_convert_into_a_zero_decimal_currency_keeps_full_precision():
    converted = convert(usd("10.01"), quote("USD", "JPY", "150.5"))
    assert converted == Money(amount=Decimal("1506.505"), currency="JPY")


def test_convert_with_rate_one_is_identity():
    assert convert(usd("480.00"), quote("USD", "USD", "1")) == usd("480.00")


def test_convert_rejects_money_in_another_currency_than_the_quote():
    with pytest.raises(CurrencyMismatchError):
        convert(eur("2200.00"), quote("USD", "EUR", "0.9276"))


def test_convert_a_mock_quote_end_to_end():
    q = MockFxProvider().quote("USD", "EUR", AS_OF)
    assert convert(usd("2100.00"), q) == eur("1947.96")


@given(
    amount=st.decimals(min_value=-10**7, max_value=10**7, places=2, allow_nan=False, allow_infinity=False),
    rate=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("500"), places=4, allow_nan=False, allow_infinity=False),
)
def test_convert_equals_amount_times_rate_exactly(amount, rate):
    converted = convert(Money(amount=amount, currency="USD"), quote("USD", "EUR", str(rate)))
    assert converted.currency == "EUR"
    assert converted.amount == amount * rate
