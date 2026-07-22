from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard

HAGER_XLSX_HEADERS = (
    "Startdatum",
    "Status",
    "Dauer",
    "Gesamte Energie (kWh)",
    "MID-zertifiziert",
    "Solarstrom (kWh)",
    "Solares Verhältnis",
    "Authentifizierung",
    "Ladestation",
)

def validate_headers(header_row: tuple[object, ...] | None) -> None:
    """
    Prüft, ob die erwarteten Hager-Spalten vorhanden und korrekt
    angeordnet sind.
    """
    if header_row is None:
        raise ValueError("Die XLSX-Datei enthält keine Kopfzeile")

    actual_headers = tuple(
        str(header_row[index] or "").strip()
        if index < len(header_row)
        else ""
        for index in range(len(HAGER_XLSX_HEADERS))
    )

    if actual_headers == HAGER_XLSX_HEADERS:
        return

    differences: list[str] = []

    for index, (expected, actual) in enumerate(
        zip(HAGER_XLSX_HEADERS, actual_headers),
        start=1,
    ):
        if expected != actual:
            differences.append(
                f"Spalte {index}: erwartet {expected!r}, "
                f"gefunden {actual!r}"
            )

    raise ValueError(
        "Ungültige XLSX-Kopfzeile. "
        + "; ".join(differences)
    )


def parse_duration(duration: str) -> timedelta:
    """
    Wandelt eine Hager-Dauerangabe in ein timedelta um.

    Beispiele:
        0h 0m 52s
        1h 23m 45s
        0h 2m 1s
    """
    normalized_duration = duration.strip()

    if not normalized_duration:
        raise ValueError("Dauer fehlt")

    match = re.fullmatch(
        r"(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?",
        normalized_duration,
    )

    if not match:
        raise ValueError(f"Ungültiges Dauerformat: {duration!r}")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return timedelta(
        hours=hours,
        minutes=minutes,
        seconds=seconds,
    )


def extract_rfid(authentication: str) -> str | None:
    """
    Extrahiert die RFID-Nummer aus dem Authentifizierungstext.

    Beispiele:
        Wartung Gottschalk (DE0D02A6) -> DE0D02A6
        RFID Nr.4 (6005E5AC)          -> 6005E5AC
        RFID N.3 (D0BEEEAC)           -> D0BEEEAC
        Keine Authentifizierung       -> None
    """
    normalized_authentication = authentication.strip()

    if not normalized_authentication:
        return None

    if normalized_authentication.lower() == "keine authentifizierung":
        return None

    match = re.search(
        r"\(([A-Za-z0-9]+)\)",
        normalized_authentication,
    )

    if not match:
        return None

    return match.group(1).upper()


def create_import_hash(
    start_time: datetime,
    station: str,
    energy: float,
    rfid: str | None,
) -> str:
    """
    Erzeugt einen stabilen SHA256-Hash zur Dublettenerkennung.

    Der Hash basiert auf:
        - Startzeit
        - Ladestation
        - Gesamtenergie
        - RFID-Nummer
    """
    hash_data = "|".join(
        [
            start_time.isoformat(),
            station.strip(),
            f"{energy:.3f}",
            rfid or "",
        ]
    )

    return hashlib.sha256(
        hash_data.encode("utf-8")
    ).hexdigest()


def parse_start_time(value: Any) -> datetime:
    """
    Wandelt den XLSX-Wert aus 'Startdatum' in datetime um.

    openpyxl kann abhängig vom Zellformat entweder einen String oder bereits
    ein datetime-Objekt liefern.
    """
    if isinstance(value, datetime):
        return value

    if value is None:
        raise ValueError("Startdatum fehlt")

    return datetime.strptime(
        str(value).strip(),
        "%d.%m.%Y %H:%M:%S",
    )


def import_xlsx(path: str | Path) -> list[dict[str, Any]]:
    """
    Liest einen Hager-Flow-XLSX-Export ein und gibt normalisierte
    Ladevorgänge zurück.

    Diese Funktion speichert noch keine Daten in der Datenbank.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"XLSX-Datei nicht gefunden: {file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Der angegebene Pfad ist keine Datei: {file_path}"
        )

    workbook = load_workbook(
        filename=file_path,
        data_only=True,
        read_only=True,
    )

    sessions: list[dict[str, Any]] = []

    try:
        sheet = workbook.active

        header_row = next(
            sheet.iter_rows(
                min_row=1,
                max_row=1,
                values_only=True,
            ),
            None,
        )

        validate_headers(header_row)

        for row_number, row in enumerate(
            sheet.iter_rows(
                min_row=2,
                max_col=len(HAGER_XLSX_HEADERS),
                values_only=True,
            ),
            start=2,
        ):
            if not row or all(value is None for value in row):
                continue

            if len(row) < 9:
                raise ValueError(
                    f"XLSX-Zeile {row_number} enthält nur "
                    f"{len(row)} statt 9 Spalten"
                )

            (
                start_value,
                status,
                duration_value,
                energy_total,
                mid_certified,
                energy_pv,
                solar_ratio,
                authentication,
                station,
            ) = row[:9]

            if start_value in (None, ""):
                continue

            try:
                start_time = parse_start_time(start_value)

                duration = parse_duration(
                    str(duration_value or "")
                )

                end_time = start_time + duration

                authentication_text = str(
                    authentication or ""
                ).strip()

                rfid = extract_rfid(authentication_text)

                energy_total_kwh = float(
                    energy_total or 0
                )

                energy_pv_kwh = float(
                    energy_pv or 0
                )

                station_id = str(
                    station or ""
                ).strip()

                if not station_id:
                    raise ValueError("Ladestation fehlt")

                import_hash = create_import_hash(
                    start_time=start_time,
                    station=station_id,
                    energy=energy_total_kwh,
                    rfid=rfid,
                )

                sessions.append(
                    {
                        "start_time": start_time,
                        "end_time": end_time,
                        "status": str(status or "").strip(),
                        "station_id": station_id,
                        "rfid": rfid,
                        "authentication": authentication_text,
                        "energy_total_kwh": energy_total_kwh,
                        "energy_pv_kwh": energy_pv_kwh,
                        "mid_certified": str(
                            mid_certified or ""
                        ).strip(),
                        "solar_ratio": str(
                            solar_ratio or ""
                        ).strip(),
                        "import_hash": import_hash,
                        "source": "xlsx",
                    }
                )

            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Fehler in XLSX-Zeile {row_number}: {exc}"
                ) from exc

    finally:
        workbook.close()

    return sessions

def import_xlsx_to_db(
    db: Session,
    path: str | Path,
) -> dict[str, int]:
    """
    Importiert Ladevorgänge aus einer Hager-XLSX-Datei in die Datenbank.

    Bereits vorhandene Datensätze werden anhand des import_hash übersprungen.
    Existiert eine RFID-Karte, wird sie dem Ladevorgang zugeordnet.
    Unbekannte oder fehlende RFID-Karten führen zu rfid_card_id=None.
    """
    parsed_sessions = import_xlsx(path)

    imported = 0
    skipped = 0
    unknown_rfid_sessions = 0
    unknown_rfid_numbers: set[str] = set()

    for session_data in parsed_sessions:
        import_hash = session_data["import_hash"]

        existing_session = db.scalar(
            select(ChargingSession.id).where(
                ChargingSession.import_hash == import_hash
            )
        )

        if existing_session is not None:
            skipped += 1
            continue

        rfid_number = session_data["rfid"]
        rfid_card_id: int | None = None

        if rfid_number is not None:
            rfid_card = db.scalar(
                select(RFIDCard).where(
                    RFIDCard.rfid_number == rfid_number
                )
            )

            if rfid_card is not None:
                rfid_card_id = rfid_card.id
            else:
                unknown_rfid_sessions += 1
                unknown_rfid_numbers.add(rfid_number)

        charging_session = ChargingSession(
            hager_session_id=None,
            station_id=session_data["station_id"],
            start_time=session_data["start_time"],
            end_time=session_data["end_time"],
            rfid_card_id=rfid_card_id,
            energy_total_kwh=session_data["energy_total_kwh"],
            energy_pv_kwh=session_data["energy_pv_kwh"],
            cost_grid_net=None,
            cost_pv_net=None,
            vat_rate=None,
            invoiced=False,
            invoice_id=None,
            import_hash=import_hash,
            source=session_data["source"],
        )

        db.add(charging_session)
        imported += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "read": len(parsed_sessions),
        "imported": imported,
        "skipped": skipped,
        "unknown_rfid_sessions": unknown_rfid_sessions,
        "unknown_rfid_numbers": sorted(unknown_rfid_numbers),
    }
