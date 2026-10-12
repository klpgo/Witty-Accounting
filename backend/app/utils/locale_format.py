"""
Formatierung von Zahlen, Beträgen und Datumsangaben nach Gebietsschema –
für Rechnungs-PDF und E-Mails. Das Frontend verwendet dieselben
Gebietsschemata über das Intl-API des Browsers.

Bewusst ohne zusätzliche Bibliothek: Witty unterstützt eine feste
Auswahl, deren Regeln hier vollständig und testbar hinterlegt sind.
Beträge erscheinen mit ISO-Währungscode (z. B. "1.234,56 EUR").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class LocaleFormat:
    label: str
    decimal_separator: str
    group_separator: str
    date_pattern: str
    currency_before: bool


NBSP = "\u00a0"

SUPPORTED_LOCALES: dict[str, LocaleFormat] = {
    "de-DE": LocaleFormat("Deutsch (Deutschland)", ",", ".", "%d.%m.%Y", False),
    "de-AT": LocaleFormat("Deutsch (Österreich)", ",", NBSP, "%d.%m.%Y", False),
    "de-CH": LocaleFormat("Deutsch (Schweiz)", ".", "’", "%d.%m.%Y", True),
    "en-GB": LocaleFormat("English (United Kingdom)", ".", ",", "%d/%m/%Y", True),
    "en-US": LocaleFormat("English (United States)", ".", ",", "%m/%d/%Y", True),
}

SUPPORTED_CURRENCIES: dict[str, str] = {
    "EUR": "Euro",
    "CHF": "Schweizer Franken",
    "GBP": "Britisches Pfund",
    "USD": "US-Dollar",
}

DEFAULT_LOCALE = "de-DE"
DEFAULT_CURRENCY = "EUR"


def locale_format(locale: str | None) -> LocaleFormat:
    return SUPPORTED_LOCALES.get(locale or DEFAULT_LOCALE, SUPPORTED_LOCALES[DEFAULT_LOCALE])


def format_decimal(value: Decimal, decimal_places: int, locale: str | None = None) -> str:
    fmt = locale_format(locale)
    quantizer = Decimal(1).scaleb(-decimal_places)
    # dieselbe Rundung wie bisher (Decimal-Standard), damit nachträglich
    # erzeugte PDFs exakt der ursprünglichen Rechnung entsprechen
    rounded = Decimal(value).quantize(quantizer)
    text = f"{rounded:,.{decimal_places}f}"

    return (
        text.replace(",", "\x00")
        .replace(".", fmt.decimal_separator)
        .replace("\x00", fmt.group_separator)
    )


def format_money(value: Decimal, currency: str | None = None, locale: str | None = None) -> str:
    amount = format_decimal(value, 2, locale)
    code = currency or DEFAULT_CURRENCY

    if locale_format(locale).currency_before:
        return f"{code} {amount}"

    return f"{amount} {code}"


def format_date(value: date, locale: str | None = None) -> str:
    return value.strftime(locale_format(locale).date_pattern)
