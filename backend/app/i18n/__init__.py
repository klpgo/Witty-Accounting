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
