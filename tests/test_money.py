"""Money: exact, currency-tagged, never mixes currencies (D-00b)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from rebooking_copilot.money import CurrencyMismatchError, Money

amounts = st.decimals(min_value=-10**9, max_value=10**9, places=2, allow_nan=False, allow_infinity=False)


def usd(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="USD")


def test_arithmetic_is_exact():
    assert usd("0.10") + usd("0.20") == usd("0.30")
    assert usd("480.00") - usd("300.00") == usd("180.00")


def test_multiply_by_passenger_count():
    assert usd("75.00") * 2 == usd("150.00")
    assert 2 * usd("75.00") == usd("150.00")


def test_multiply_rejects_float():
    with pytest.raises(TypeError):
        usd("75.00") * 1.5


def test_mixing_currencies_raises():
    eur = Money(amount=Decimal("2200.00"), currency="EUR")
    with pytest.raises(CurrencyMismatchError):
        eur - usd("2100.00")
    with pytest.raises(CurrencyMismatchError):
        eur + usd("0.00")
    with pytest.raises(CurrencyMismatchError):
        eur > usd("2100.00")


def test_equality_ignores_trailing_zeros_but_not_currency():
    assert usd("1.0") == usd("1.00")
    assert usd("1.00") != Money(amount=Decimal("1.00"), currency="EUR")


def test_ordering_same_currency():
    assert usd("80.00") > usd("25.00")
    assert usd("-90.00") < Money.zero("USD")


@pytest.mark.parametrize("bad", [0.1, True, "abc", "NaN", "Infinity"])
def test_amount_must_be_exact_and_finite(bad):
    with pytest.raises(ValidationError):
        Money(amount=bad, currency="USD")


@pytest.mark.parametrize("ok", [Decimal("1.25"), 3, "4.50"])
def test_amount_accepts_exact_inputs(ok):
    assert Money(amount=ok, currency="USD").amount == Decimal(str(ok))


@pytest.mark.parametrize("bad", ["usd", "US", "XXX", "DOLLAR"])
def test_currency_must_be_a_known_iso_code(bad):
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), currency=bad)


def test_str_uses_minor_units():
    assert str(usd("80")) == "80.00 USD"
    assert str(Money(amount=Decimal("1234.5"), currency="JPY")) == "1234 JPY"


def test_money_is_immutable():
    m = usd("1.00")
    with pytest.raises(ValidationError):
        m.amount = Decimal("2.00")


@given(amounts, amounts)
def test_addition_commutes_and_subtraction_inverts(a, b):
    x, y = Money(amount=a, currency="EUR"), Money(amount=b, currency="EUR")
    assert x + y == y + x
    assert (x + y) - y == x
