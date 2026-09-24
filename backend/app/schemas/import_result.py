from datetime import date

from pydantic import BaseModel


class ImportResult(BaseModel):
    read: int
    imported: int
    skipped: int
    # alle Ladevorgänge/Nummern ohne Zuordnung (Summe der Ursachen)
    unknown_rfid_sessions: int
    unknown_rfid_numbers: list[str]
    priced: int
    missing_price: int
    invalid_energy: int
    # aufgeschlüsselt nach Ursache
    unknown_rfid_cards: list[str] = []
    inactive_rfid_cards: list[str] = []
    unassigned_rfid_numbers: list[str] = []
    # bei vorhandenen Ladevorgängen ergänzte RFID-Nummern
    backfilled_rfid_numbers: int = 0
    # ältere Ladevorgänge, die jetzt einer Zuordnung zugeordnet wurden
    reassigned_sessions: int = 0
    # Hager-Abruf: frühester abgerufener Tag (None = alles)
    fetched_from: date | None = None
