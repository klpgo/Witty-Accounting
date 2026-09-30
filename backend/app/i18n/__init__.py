"""
Übersetzungen im Backend (Rechnungen, Rechnungs-PDF, Rechnungs-E-Mails).

Die Sprache einer Rechnung wird beim Anlegen festgehalten (Invoice.language).
Ältere Rechnungen ohne Angabe verwenden Deutsch.
"""
from __future__ import annotations

from app.i18n import de, en

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

_CATALOGS: dict[str, dict[str, str]] = {
    "de": de.MESSAGES,
    "en": en.MESSAGES,
}


def normalize_language(language: str | None) -> str:
    return language if language in _CATALOGS else DEFAULT_LANGUAGE


def translate(language: str | None, key: str, **params: object) -> str:
    """Text zum Schlüssel in der Sprache; fehlt er, gilt Deutsch."""
    catalog = _CATALOGS[normalize_language(language)]
    text = catalog.get(key) or de.MESSAGES[key]

    return text.format(**params) if params else text


# Zweisprachige E-Mails (Konto- und Test-E-Mails): Deutsch oben, Englisch
# darunter, getrennt durch eine Linie. Für Empfänger, deren Sprache beim
# Versand nicht feststeht (z. B. Einladung).
BILINGUAL_SEPARATOR = "\n" + "-" * 40 + "\n\n"


def bilingual_subject(key: str, **params: object) -> str:
    """Betreff "Deutsch / English"; bei gleichem Text nur einmal."""
    german = translate("de", key, **params)
    english = translate("en", key, **params)

    return german if german == english else f"{german} / {english}"


def bilingual_text(render) -> str:
    """Text zweisprachig: render(language) liefert den Text je Sprache."""
    return (
        translate("de", "email.englishBelow")
        + "\n\n"
        + render("de")
        + BILINGUAL_SEPARATOR
        + render("en")
    )
