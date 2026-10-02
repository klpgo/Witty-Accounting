"""
Abruf von Ladevorgängen direkt aus der Hager Cloud.

Nutzt die auf der Einstellungsseite hinterlegten Zugangsdaten, meldet
sich ohne Browser an (hager_client) und übergibt die Sessions an den
JSON-Importer (Dublettenprüfung, RFID-Zuordnung).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Callable, TypeVar

import httpx

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings
from app.services import hager_client
from app.services.hager_secret import decrypt_hager_password
from app.services.hager_token_cache import token_cache
from app.services.data_timezone import ensure_data_timezone
from app.services.import_lock import import_lock
from app.services.wallboxes import (
    display_names,
    ensure_wallboxes,
    update_hager_names,
)
from app.services.importers.hager_json_importer import (
    import_charging_rows_to_db,
    parse_utc_to_local,
)
from app.utils.local_time import LOCAL_TIMEZONE
from app.utils.utc import utc_now


logger = logging.getLogger(__name__)

T = TypeVar("T")


class HagerConfigurationError(Exception):
    """Zugangsdaten oder Installations-ID fehlen."""


class HagerConnectionError(Exception):
    """Hager Cloud nicht erreichbar oder Anmeldung/Abruf fehlgeschlagen."""


@dataclass(frozen=True)
class HagerAccess:
    username: str
    password: str
    installation_id: str
    serial_number: str


def load_access(db: Session) -> HagerAccess:
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is None:
        raise HagerConfigurationError(
            "The global settings were not found."
        )

    missing = [
        label
        for label, value in (
            ("username", global_settings.hager_username),
            ("password", global_settings.hager_password_encrypted),
            ("installation ID", global_settings.hager_installation_id),
            ("serial number", global_settings.hager_serial_number),
        )
        if not value
    ]

    if missing:
        raise HagerConfigurationError(
            "The following are missing for fetching from the Hager Cloud: "
            + ", ".join(missing)
        )

    return HagerAccess(
        username=global_settings.hager_username,
        password=decrypt_hager_password(
            global_settings.hager_password_encrypted
        ),
        installation_id=global_settings.hager_installation_id,
        serial_number=global_settings.hager_serial_number,
    )


def call_with_token(
    access: HagerAccess,
    call: Callable[[str], T],
    force_login: bool = False,
) -> T:
    """
    Führt einen API-Aufruf mit einem Zugriffstoken aus dem Token-Cache
    (Arbeitsspeicher) aus. Lehnt die API es ab (401/403) oder antwortet
    sie nicht (Timeout), wird einmal neu angemeldet und wiederholt.
    """
    try:
        token = token_cache.get_access_token(
            access.username,
            access.password,
            force_login=force_login,
        )

        try:
            return call(token)
        except (
            hager_client.HagerUnauthorizedError,
            httpx.TimeoutException,
        ) as exc:
            if force_login:
                raise

            logger.warning(
                "Hager: fetch with stored token failed (%s), signing in "
                "again and retrying",
                type(exc).__name__,
            )
            token_cache.invalidate(access.username)
            token = token_cache.get_access_token(
                access.username,
                access.password,
                force_login=True,
            )

            return call(token)
    except (
        hager_client.HagerLoginError,
        hager_client.HagerApiError,
    ) as exc:
        raise HagerConnectionError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HagerConnectionError(
            f"Hager Cloud is not reachable: {type(exc).__name__}"
        ) from exc


def fetch_all_sessions(
    access: HagerAccess,
    force_login: bool = False,
    **fetch_options: Any,
) -> list[dict[str, Any]]:
    """
    Ladevorgänge aller Wallboxen über den E-Mobility-Endpunkt
    (fetch_options siehe hager_client.fetch_charging_sessions,
    z. B. stop_before).
    """
    return call_with_token(
        access,
        lambda token: hager_client.fetch_charging_sessions(
            token,
            access.serial_number,
            **fetch_options,
        ),
        force_login=force_login,
    )


def wallbox_names(
    db: Session,
    access: HagerAccess,
    wallbox_ids: set[str] | None = None,
) -> dict[str, str]:
    """
    Angezeigte Namen der Wallboxen ({Wallbox-ID: Name}) aus der Tabelle der
    Wallboxen. Vorher werden die Namen aus der Hager Cloud übernommen und
    für unbekannte IDs Einträge angelegt. Ist die Namensliste der Hager
    Cloud nicht abrufbar, gelten die gespeicherten Namen – der Import
    scheitert daran nicht.
    """
    try:
        update_hager_names(
            db,
            call_with_token(
                access,
                lambda token: hager_client.fetch_wallbox_names(
                    token,
                    access.installation_id,
                ),
            ),
        )
    except HagerConnectionError as exc:
        logger.warning("Hager: wallbox names not available: %s", exc)

    ensure_wallboxes(db, wallbox_ids or set())

    return display_names(db)


def session_local_start(item: dict[str, Any]) -> datetime | None:
    value = item.get("startAt")

    if value is None:
        session = item.get("session")
        value = session.get("start_date_time") if isinstance(session, dict) else None

    try:
        return parse_utc_to_local(value, "startAt")
    except ValueError:
        return None


def check_connection(db: Session) -> dict[str, object]:
    """Anmeldung und Abruf prüfen, ohne etwas zu importieren.
    Meldet sich immer neu an, damit die Zugangsdaten wirklich
    geprüft werden. Ruft nur die erste Seite ab (neueste zuerst)."""
    rows = fetch_all_sessions(
        load_access(db),
        force_login=True,
        max_pages=1,
    )
    starts = [
        start
        for start in map(session_local_start, rows)
        if start is not None
    ]

    return {
        # der Endpunkt nennt keine Gesamtzahl
        "sessions": None,
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


def record_successful_fetch(db: Session, fetched_at: datetime) -> None:
    """
    Schreibt den Zeitpunkt des letzten erfolgreichen Abrufs als gezieltes
    UPDATE in einer frischen Transaktion. Ein Zurückschreiben der zuvor
    gelesenen Zeile würde bei MariaDB (Snapshot-Isolation) mit Fehler 1020
    scheitern, wenn die Einstellungen inzwischen geändert wurden.
    """
    db.commit()
    db.execute(
        update(GlobalSettings)
        .where(GlobalSettings.id == 1)
        .values(hager_last_successful_fetch_at=fetched_at)
    )
    db.commit()
    db.expire_all()


def import_from_hager(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    fetch_all: bool = False,
) -> dict[str, object]:
    """
    Ruft Sessions aus der Hager Cloud ab und importiert sie.

    - fetch_all: alle Sessions ab Abrechnungsbeginn (vollständiger Abgleich)
    - date_from/date_to: nur dieser Zeitraum, frühestens ab Abrechnungsbeginn
    - sonst: ab dem Cut-off (letzter erfolgreicher Abruf minus 3 Tage,
      frühestens Abrechnungsbeginn)

    Bereits vorhandene Sessions überspringt die Dublettenprüfung. Nur
    Abrufe bis "jetzt" (ohne Zeitraum) schreiben den Zeitpunkt des
    letzten erfolgreichen Abrufs fort.
    """
    with import_lock(db):
        ensure_data_timezone(db)
        return _import_from_hager(db, date_from, date_to, fetch_all)


def _import_from_hager(
    db: Session,
    date_from: date | None,
    date_to: date | None,
    fetch_all: bool,
) -> dict[str, object]:
    access = load_access(db)
    global_settings = db.get(GlobalSettings, 1)

    billing_start = global_settings.billing_start_date

    if fetch_all:
        # "alle" heißt: alle ab Abrechnungsbeginn
        effective_from = billing_start
    elif date_from is not None:
        effective_from = (
            max(date_from, billing_start)
            if billing_start is not None
            else date_from
        )
    else:
        effective_from = determine_cutoff(
            global_settings.hager_last_successful_fetch_at,
            billing_start,
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
        "Hager: %s charging sessions fetched on %s page(s), from %s",
        len(items),
        info.get("pages", "?"),
        effective_from.isoformat() if effective_from else "Beginn",
    )

    result = import_charging_rows_to_db(
        db,
        filter_by_local_date(items, effective_from, date_to),
        wallbox_names(
            db,
            access,
            {
                str(row.get("wallboxID") or "").strip()
                for row in items
                if row.get("wallboxID")
            },
        ),
    )

    if date_from is None and date_to is None:
        record_successful_fetch(db, fetch_started_at)

    result["fetched_from"] = effective_from

    return result
