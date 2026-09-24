"""
Abruf von Ladevorgängen direkt aus Hager flow.

Nutzt die auf der Einstellungsseite hinterlegten Zugangsdaten, meldet
sich ohne Browser an (hager_client) und übergibt die Sessions an den
JSON-Importer (Dublettenprüfung, RFID-Zuordnung).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx

from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings
from app.services import hager_client
from app.services.hager_secret import decrypt_hager_password
from app.services.hager_token_cache import token_cache
from app.services.importers.hager_json_importer import (
    import_items_to_db,
    parse_utc_to_local,
)
from app.utils.local_time import LOCAL_TIMEZONE
from app.utils.utc import utc_now


logger = logging.getLogger(__name__)


class HagerConfigurationError(Exception):
    """Zugangsdaten oder Installations-ID fehlen."""


class HagerConnectionError(Exception):
    """Hager flow nicht erreichbar oder Anmeldung/Abruf fehlgeschlagen."""


@dataclass(frozen=True)
class HagerAccess:
    username: str
    password: str
    installation_id: str


def load_access(db: Session) -> HagerAccess:
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is None:
        raise HagerConfigurationError(
            "Die globalen Einstellungen wurden nicht gefunden."
        )

    missing = [
        label
        for label, value in (
            ("Benutzername", global_settings.hager_username),
            ("Passwort", global_settings.hager_password_encrypted),
            ("Installations-ID", global_settings.hager_installation_id),
        )
        if not value
    ]

    if missing:
        raise HagerConfigurationError(
            "Für den Abruf aus Hager flow fehlen: "
            + ", ".join(missing)
        )

    return HagerAccess(
        username=global_settings.hager_username,
        password=decrypt_hager_password(
            global_settings.hager_password_encrypted
        ),
        installation_id=global_settings.hager_installation_id,
    )


def fetch_all_sessions(
    access: HagerAccess,
    force_login: bool = False,
    **fetch_options: Any,
) -> list[dict[str, Any]]:
    """
    Sessions der Installation abrufen (fetch_options siehe
    hager_client.fetch_sessions, z. B. stop_before).

    Das Zugriffstoken kommt aus dem Token-Cache (Arbeitsspeicher). Lehnt
    die API es ab (401/403) oder antwortet sie nicht (Timeout), wird
    einmal neu angemeldet und wiederholt.
    """
    try:
        token = token_cache.get_access_token(
            access.username,
            access.password,
            force_login=force_login,
        )

        try:
            return hager_client.fetch_sessions(
                token,
                access.installation_id,
                **fetch_options,
            )
        except (
            hager_client.HagerUnauthorizedError,
            httpx.TimeoutException,
        ) as exc:
            if force_login:
                raise

            logger.warning(
                "Hager: Abruf mit gespeichertem Token "
                "fehlgeschlagen (%s), melde neu an und "
                "wiederhole",
                type(exc).__name__,
            )
            token_cache.invalidate(access.username)
            token = token_cache.get_access_token(
                access.username,
                access.password,
                force_login=True,
            )

            return hager_client.fetch_sessions(
                token,
                access.installation_id,
                **fetch_options,
            )
    except (
        hager_client.HagerLoginError,
        hager_client.HagerApiError,
    ) as exc:
        raise HagerConnectionError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HagerConnectionError(
            "Hager flow ist nicht erreichbar: "
            f"{type(exc).__name__}"
        ) from exc


def session_local_start(item: dict[str, Any]) -> datetime | None:
    session = item.get("session")

    if not isinstance(session, dict):
        return None

    try:
        return parse_utc_to_local(
            session.get("start_date_time"),
            "start_date_time",
        )
    except ValueError:
        return None


def check_connection(db: Session) -> dict[str, object]:
    """Anmeldung und Abruf prüfen, ohne etwas zu importieren.
    Meldet sich immer neu an, damit die Zugangsdaten wirklich
    geprüft werden. Ruft nur die erste Seite ab (neueste zuerst)."""
    info: dict[str, Any] = {}
    items = fetch_all_sessions(
        load_access(db),
        force_login=True,
        max_pages=1,
        info=info,
    )
    starts = [
        start
        for start in map(session_local_start, items)
        if start is not None
    ]
    total = info.get("total_elements")

    return {
        "sessions": total if isinstance(total, int) else len(items),
        "latest_session_start": max(starts) if starts else None,
    }


def filter_by_local_date(
    items: list[dict[str, Any]],
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    if date_from is None and date_to is None:
        return items

    selected = []

    for item in items:
        start = session_local_start(item)

        if start is None:
            continue

        if date_from is not None and start.date() < date_from:
            continue

        if date_to is not None and start.date() > date_to:
            continue

        selected.append(item)

    return selected


# Überlappung zum letzten erfolgreichen Abruf: fängt Ladevorgänge ab, die
# damals noch liefen oder bei Hager verspätet eintreffen
FETCH_OVERLAP = timedelta(days=3)


def determine_cutoff(
    last_successful_fetch_at: datetime | None,
    billing_start_date: date | None,
) -> date | None:
    """
    Frühester Tag (Ortszeit), ab dem abgerufen wird:
    letzter erfolgreicher Abruf minus Überlappung, aber nie vor dem
    Abrechnungsbeginn. None = alles abrufen.
    """
    candidates: list[date] = []

    if last_successful_fetch_at is not None:
        last_utc = (
            last_successful_fetch_at.replace(tzinfo=UTC)
            if last_successful_fetch_at.tzinfo is None
            else last_successful_fetch_at
        )
        candidates.append(
            (last_utc - FETCH_OVERLAP).astimezone(LOCAL_TIMEZONE).date()
        )

    if billing_start_date is not None:
        candidates.append(billing_start_date)

    return max(candidates) if candidates else None


def local_day_start(day: date) -> datetime:
    """Beginn des Tages in Ortszeit als UTC-Zeitpunkt."""
    return datetime.combine(day, time(0, 0), tzinfo=LOCAL_TIMEZONE).astimezone(UTC)


def import_from_hager(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    fetch_all: bool = False,
) -> dict[str, object]:
    """
    Ruft Sessions aus Hager flow ab und importiert sie.

    - fetch_all: alle verfügbaren Sessions (vollständiger Abgleich)
    - date_from/date_to: nur dieser Zeitraum
    - sonst: ab dem Cut-off (letzter erfolgreicher Abruf minus 3 Tage,
      frühestens Abrechnungsbeginn)

    Bereits vorhandene Sessions überspringt die Dublettenprüfung. Nur
    Abrufe bis "jetzt" (ohne Zeitraum) schreiben den Zeitpunkt des
    letzten erfolgreichen Abrufs fort.
    """
    access = load_access(db)
    global_settings = db.get(GlobalSettings, 1)

    if fetch_all:
        effective_from = None
    elif date_from is not None:
        effective_from = date_from
    else:
        effective_from = determine_cutoff(
            global_settings.hager_last_successful_fetch_at,
            global_settings.billing_start_date,
        )

    fetch_started_at = utc_now()
    info: dict[str, Any] = {}
    items = fetch_all_sessions(
        access,
        stop_before=(
            local_day_start(effective_from)
            if effective_from is not None
            else None
        ),
        info=info,
    )
    logger.info(
        "Hager: %s Sessions auf %s Seite(n) abgerufen, ab %s",
        len(items),
        info.get("pages", "?"),
        effective_from.isoformat() if effective_from else "Beginn",
    )

    result = import_items_to_db(
        db,
        filter_by_local_date(items, effective_from, date_to),
    )

    if date_from is None and date_to is None:
        global_settings = db.get(GlobalSettings, 1)
        global_settings.hager_last_successful_fetch_at = fetch_started_at
        db.commit()

    result["fetched_from"] = effective_from

    return result
