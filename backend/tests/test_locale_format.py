from datetime import date
from decimal import Decimal

import pytest

from app.schemas.settings import CurrencyCode, LocaleCode
from app.utils.locale_format import (
    SUPPORTED_CURRENCIES,
    SUPPORTED_LOCALES,
    format_date,
    format_decimal,
    format_money,
)


@pytest.mark.parametrize(
    ("locale", "money", "day"),
    [
        ("de-DE", "1.234,56 EUR", "05.09.2026"),
        ("de-AT", "1\u00a0234,56 EUR", "05.09.2026"),
        ("de-CH", "EUR 1’234.56", "05.09.2026"),
        ("en-GB", "EUR 1,234.56", "05/09/2026"),
        ("en-US", "EUR 1,234.56", "09/05/2026"),
    ],
)
def test_formats_per_locale(locale: str, money: str, day: str) -> None:
    assert format_money(Decimal("1234.56"), "EUR", locale) == money
    assert format_date(date(2026, 9, 5), locale) == day


def test_default_and_unknown_locale_use_german_format() -> None:
    assert format_money(Decimal("2.62")) == "2,62 EUR"
    assert format_money(Decimal("2.62"), "EUR", "xx-XX") == "2,62 EUR"


def test_rounding_matches_previous_pdf_output() -> None:
    # bisherige Rundung (Decimal-Standard): PDFs bleiben reproduzierbar
    assert format_decimal(Decimal("0.25"), 1) == "0,2"
    assert format_decimal(Decimal("0.35"), 1) == "0,4"
    assert format_decimal(Decimal("-3.05"), 1) == "-3,0"


def test_schema_choices_match_supported_values() -> None:
    assert set(LocaleCode.__args__) == set(SUPPORTED_LOCALES)
    assert set(CurrencyCode.__args__) == set(SUPPORTED_CURRENCIES)
