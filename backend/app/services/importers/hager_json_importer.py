"""
Import von Hager-Ladevorgängen im JSON-Format.

Akzeptierte Eingaben:
    - Ausgabe von hager-fetch: {"sessions": [...], ...}
    - rohe Seite der Hager-Bridge-API: {"content": [...], ...}
    - eine Liste von Session-Objekten

Zeitstempel liefert die API in UTC. Gespeichert werden sie wie beim
XLSX-Import als lokale, naive Zeit (Europe/Berlin).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.services.importers.xlsx_importer import create_import_hash
from app.services.data_timezone import ensure_data_timezone
from app.services.importers.import_filters import (
    ExclusionCounter,
    ImportFilters,
    exclusion_reason,
    load_import_filters,
)
from app.services.rfid_reassignment import (
    ASSIGNED,
    RFIDIssueCollector,
    classify_rfid,
    reassign_open_sessions,
)
from app.utils.local_time import LOCAL_TIMEZONE


JSON_SOURCE = "json"


def extract_session_items(payload: Any) -> list[dict[str, Any]]:
    """Liefert die Session-Objekte aus den unterstützten Formaten."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
        items = payload["sessions"]
    elif isinstance(payload, dict) and isinstance(payload.get("content"), list):
        items = payload["content"]
    else:
        raise ValueError(
            "Unknown JSON format: expected the output of hager-fetch or "
            "a response of the Hager API."
        )

    if not all(isinstance(item, dict) for item in items):
        raise ValueError("The JSON file contains invalid session entries.")

    return items


def parse_utc_to_local(value: Any, field_name: str) -> datetime:
    """'2026-07-15T09:26:37Z' -> naive lokale Zeit (Europe/Berlin)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} missing")

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp in {field_name}: {value!r}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def station_label(item: dict[str, Any]) -> str:
    """
    Bezeichnung der Ladestation wie im XLSX-Export: Name der Wallbox,
    ersatzweise 'ID: <wallboxId>'.
    """
    name = str(item.get("wallboxName") or "").strip()

    if name:
        return name

    wallbox_id = str(item.get("wallboxId") or "").strip()

    if wallbox_id:
        return f"ID: {wallbox_id}"

    raise ValueError("charging station missing")


def station_aliases(item: dict[str, Any]) -> set[str]:
    """Alle Bezeichnungen, unter denen die Station per XLSX importiert
    worden sein kann."""
    aliases: set[str] = set()
    name = str(item.get("wallboxName") or "").strip()
    wallbox_id = str(item.get("wallboxId") or "").strip()

    if name:
        aliases.add(name)

    if wallbox_id:
        aliases.add(f"ID: {wallbox_id}")

    return aliases


def to_float(value: Any, field_name: str) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value in {field_name}: {value!r}") from exc


def parse_session(item: dict[str, Any]) -> dict[str, Any] | None:
    """
    Normalisiert eine Hager-Session auf dieselbe Struktur wie der
    XLSX-Importer. Gibt None zurück, wenn die Session noch läuft
    (kein Endzeitpunkt).
    """
    session = item.get("session")

    if not isinstance(session, dict):
        raise ValueError("field 'session' missing")

    if not session.get("end_date_time"):
        return None

    hager_session_id = str(
        session.get("id") or item.get("emobilitySessionId") or ""
    ).strip()

    if not hager_session_id:
        raise ValueError("session ID missing")

    start_time = parse_utc_to_local(session.get("start_date_time"), "start_date_time")
    end_time = parse_utc_to_local(session.get("end_date_time"), "end_date_time")

    if end_time < start_time:
        raise ValueError("end time is before the start time")

    station_id = station_label(item)
    rfid_raw = str(item.get("emobilityToken") or "").strip()
    rfid = rfid_raw.upper() or None
    energy_total_kwh = to_float(session.get("kwh"), "kwh")
    energy_pv_kwh = to_float(item.get("energySolar"), "energySolar")

    return {
        "hager_session_id": hager_session_id,
        "start_time": start_time,
        "end_time": end_time,
        "status": str(item.get("status") or session.get("status") or "").strip(),
        "station_id": station_id,
        "station_aliases": station_aliases(item),
        "wallbox_id": str(item.get("wallboxId") or "").strip() or None,
        "rfid": rfid,
        "energy_total_kwh": energy_total_kwh,
        "energy_pv_kwh": energy_pv_kwh,
        "import_hash": create_import_hash(
            start_time=start_time,
            station=station_id,
            energy=energy_total_kwh,
            rfid=rfid,
        ),
        "source": JSON_SOURCE,
    }


HAGER_API_SOURCE = "hager"
WH_PER_KWH = 1000.0


def parse_charging_row(
    row: dict[str, Any],
    wallbox_names: dict[str, str],
) -> dict[str, Any] | None:
    """
    Normalisiert einen Datensatz des E-Mobility-Endpunkts.

    Energie liefert die API in Wh, Zeiten in UTC. Gibt None zurück,
    wenn der Ladevorgang noch läuft (kein Endzeitpunkt).
    """
    if not row.get("stopAt"):
        return None

    session_id = str(row.get("sessionID") or "").strip()

    if not session_id:
        raise ValueError("sessionID missing")

    wallbox_id = str(row.get("wallboxID") or "").strip()

    if not wallbox_id:
        raise ValueError("wallboxID missing")

    start_time = parse_utc_to_local(row.get("startAt"), "startAt")
    end_time = parse_utc_to_local(row.get("stopAt"), "stopAt")

    if end_time < start_time:
        raise ValueError("end time is before the start time")

    station_id = wallbox_names.get(wallbox_id) or f"ID: {wallbox_id}"
    rfid = str(row.get("authData") or "").strip().upper() or None
    energy_total_kwh = to_float(row.get("energyAll"), "energyAll") / WH_PER_KWH
    energy_pv_kwh = to_float(row.get("energySolar"), "energySolar") / WH_PER_KWH

    return {
        "hager_session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "status": str(row.get("status") or "").strip(),
        "station_id": station_id,
        "station_aliases": {station_id, f"ID: {wallbox_id}"},
        "wallbox_id": wallbox_id,
        "rfid": rfid,
        "energy_total_kwh": energy_total_kwh,
        "energy_pv_kwh": energy_pv_kwh,
        "import_hash": create_import_hash(
            start_time=start_time,
            station=station_id,
            energy=energy_total_kwh,
            rfid=rfid,
        ),
        "source": HAGER_API_SOURCE,
    }


def parse_charging_rows(
    rows: list[dict[str, Any]],
    wallbox_names: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """Rückgabe: (normalisierte Sessions, Anzahl laufender Sessions)."""
    sessions: list[dict[str, Any]] = []
    running = 0

    for index, row in enumerate(rows, start=1):
        try:
            parsed = parse_charging_row(row, wallbox_names)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Error in charging session {index}: {exc}") from exc

        if parsed is None:
            running += 1
        else:
            sessions.append(parsed)

    return sessions, running


def import_json(path: str | Path) -> tuple[list[dict[str, Any]], int]:
    """
    Liest eine JSON-Datei ein.

    Rückgabe: (normalisierte Sessions, Anzahl übersprungener laufender
    Sessions).
    """
    file_path = Path(path)

    if not file_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"The file is not valid JSON: {exc}") from exc

    return parse_items(extract_session_items(payload))


def parse_items(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Normalisiert Session-Objekte der Hager-API.

    Rückgabe: (normalisierte Sessions, Anzahl übersprungener laufender
    Sessions).
    """
    sessions: list[dict[str, Any]] = []
    running = 0

    for index, item in enumerate(items, start=1):
        try:
            parsed = parse_session(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Error in session {index}: {exc}") from exc

        if parsed is None:
            running += 1
        else:
            sessions.append(parsed)

    return sessions, running


def find_existing_session(
    db: Session,
    session_data: dict[str, Any],
) -> ChargingSession | None:
    """
    Dublettenprüfung in drei Stufen:
        1. gleiche Hager-Session-ID
        2. gleicher Import-Hash
        3. gleiche Startzeit (auf die Sekunde) und gleiche Wallbox – oder,
           bei früher importierten Ladevorgängen ohne Wallbox-ID, gleiche
           Station bzw. einziger Ladevorgang zu dieser Sekunde
    """
    existing = db.scalar(
        select(ChargingSession).where(
            ChargingSession.hager_session_id == session_data["hager_session_id"]
        )
    )

    if existing is not None:
        return existing

    existing = db.scalar(
        select(ChargingSession).where(
            ChargingSession.import_hash == session_data["import_hash"]
        )
    )

    if existing is not None:
        return existing

    candidates = db.scalars(
        select(ChargingSession).where(
            ChargingSession.start_time == session_data["start_time"]
        )
    ).all()
    wallbox_id = session_data.get("wallbox_id")

    # a) gleiche Wallbox
    if wallbox_id:
        for candidate in candidates:
            if candidate.wallbox_id == wallbox_id:
                return candidate

    # b) früher importiert (ohne Wallbox-ID) an derselben Station
    legacy = [c for c in candidates if c.wallbox_id is None]

    for candidate in legacy:
        if candidate.station_id in session_data["station_aliases"]:
            return candidate

    # c) früher importiert, Station anders benannt (z. B. getauschte
    #    Wallbox): nur wenn es der einzige Ladevorgang zu dieser Sekunde ist
    if len(candidates) == 1 and len(legacy) == 1:
        return legacy[0]

    return None


def is_editable(charging_session: ChargingSession) -> bool:
    """Abgerechnete Ladevorgänge werden nicht verändert."""
    return (
        not charging_session.invoiced
        and charging_session.invoice_id is None
    )


def backfill_existing_session(
    existing: ChargingSession,
    session_data: dict[str, Any],
) -> bool:
    """
    Ergänzt bei einem bereits vorhandenen, nicht abgerechneten
    Ladevorgang fehlende RFID-Nummer und Hager-ID.
    Rückgabe: True, wenn die RFID-Nummer ergänzt wurde.
    """
    if not is_editable(existing):
        return False

    if existing.hager_session_id is None:
        existing.hager_session_id = session_data["hager_session_id"]

    if existing.wallbox_id is None and session_data.get("wallbox_id"):
        existing.wallbox_id = session_data["wallbox_id"]

    if existing.rfid_number is None and session_data["rfid"] is not None:
        existing.rfid_number = session_data["rfid"]
        return True

    return False


def import_json_to_db(
    db: Session,
    path: str | Path,
) -> dict[str, object]:
    """
    Importiert Ladevorgänge aus einer Hager-JSON-Datei.

    Rückgabe im selben Format wie import_xlsx_to_db.
    """
    ensure_data_timezone(db)
    parsed_sessions, running_sessions = import_json(path)

    return import_parsed_sessions_to_db(
        db,
        parsed_sessions,
        running_sessions,
    )


def import_items_to_db(
    db: Session,
    items: list[dict[str, Any]],
) -> dict[str, object]:
    """Importiert Session-Objekte direkt aus der Hager-API."""
    parsed_sessions, running_sessions = parse_items(items)

    return import_parsed_sessions_to_db(
        db,
        parsed_sessions,
        running_sessions,
    )


def import_charging_rows_to_db(
    db: Session,
    rows: list[dict[str, Any]],
    wallbox_names: dict[str, str],
) -> dict[str, object]:
    """Importiert Datensätze des E-Mobility-Endpunkts."""
    parsed_sessions, running_sessions = parse_charging_rows(rows, wallbox_names)

    return import_parsed_sessions_to_db(
        db,
        parsed_sessions,
        running_sessions,
    )


def import_parsed_sessions_to_db(
    db: Session,
    parsed_sessions: list[dict[str, Any]],
    running_sessions: int = 0,
    filters: ImportFilters | None = None,
) -> dict[str, object]:
    """
    Speichert normalisierte Sessions mit Dublettenprüfung.
    Ohne `filters` gelten die Import-Regeln aus den Einstellungen
    (Abrechnungsbeginn, Vorgänge ohne Energie).
    """
    filters = filters if filters is not None else load_import_filters(db)
    excluded = ExclusionCounter()

    imported = 0
    skipped = running_sessions
    backfilled = 0
    issues = RFIDIssueCollector()
    imported_hashes: list[str] = []
    seen_ids: set[str] = set()

    for session_data in parsed_sessions:
        reason = exclusion_reason(
            filters,
            session_data["start_time"],
            session_data["energy_total_kwh"],
        )

        if reason is not None:
            excluded.add(reason)
            continue

        if session_data["hager_session_id"] in seen_ids:
            skipped += 1
            continue

        seen_ids.add(session_data["hager_session_id"])

        existing = find_existing_session(db, session_data)

        if existing is not None:
            skipped += 1

            if backfill_existing_session(existing, session_data):
                backfilled += 1

            continue

        rfid_number = session_data["rfid"]
        rfid_card_id: int | None = None
        rfid_assignment_id: int | None = None

        if rfid_number is not None:
            status, assignment = classify_rfid(
                db,
                rfid_number,
                session_data["start_time"],
            )

            if status == ASSIGNED and assignment is not None:
                rfid_card_id = assignment.rfid_card_id
                rfid_assignment_id = assignment.id
            else:
                issues.add(status, rfid_number)

        db.add(
            ChargingSession(
                hager_session_id=session_data["hager_session_id"],
                station_id=session_data["station_id"],
                wallbox_id=session_data.get("wallbox_id"),
                start_time=session_data["start_time"],
                end_time=session_data["end_time"],
                rfid_number=rfid_number,
                rfid_card_id=rfid_card_id,
                rfid_assignment_id=rfid_assignment_id,
                energy_total_kwh=session_data["energy_total_kwh"],
                energy_pv_kwh=session_data["energy_pv_kwh"],
                cost_grid_net=None,
                cost_pv_net=None,
                vat_rate=None,
                invoiced=False,
                invoice_id=None,
                import_hash=session_data["import_hash"],
                source=session_data["source"],
            )
        )
        imported += 1
        imported_hashes.append(session_data["import_hash"])

    db.flush()
    reassigned = reassign_open_sessions(db)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "read": len(parsed_sessions) + running_sessions,
        "imported": imported,
        "skipped": skipped,
        **issues.as_result(),
        **excluded.as_result(),
        "backfilled_rfid_numbers": backfilled,
        "reassigned_sessions": reassigned,
        "imported_hashes": imported_hashes,
    }
