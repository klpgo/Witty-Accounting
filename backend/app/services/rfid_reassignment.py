"""
Einordnung von RFID-Nummern beim Import und nachträgliche Zuordnung
von Ladevorgängen.

Ein Ladevorgang wird der Benutzerzuordnung zugeordnet, die zum
Ladezeitpunkt gültig war. Fehlt sie beim Import, bleibt die RFID-Nummer
am Ladevorgang gespeichert; sobald eine passende Zuordnung angelegt
wird, holt reassign_open_sessions() die Verknüpfung nach.
Abgerechnete Ladevorgänge werden nie verändert.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.services.rfid_assignments import (
    RFIDAssignmentOverlapError,
    resolve_rfid_assignment,
)


logger = logging.getLogger(__name__)

ASSIGNED = "assigned"
UNKNOWN_CARD = "unknown_card"
INACTIVE_CARD = "inactive_card"
NO_ASSIGNMENT = "no_assignment"


def classify_rfid(
    db: Session,
    rfid_number: str,
    at: datetime,
) -> tuple[str, RFIDCardAssignment | None]:
    """Ordnet eine RFID-Nummer zum Zeitpunkt `at` ein."""
    try:
        assignment = resolve_rfid_assignment(
            db,
            rfid_number=rfid_number,
            at=at,
        )
    except RFIDAssignmentOverlapError:
        logger.warning(
            "Mehrere gültige Zuordnungen für RFID %s am %s",
            rfid_number,
            at.isoformat(),
        )
        return NO_ASSIGNMENT, None

    if assignment is not None:
        return ASSIGNED, assignment

    card_active = db.scalar(
        select(RFIDCard.active).where(
            RFIDCard.rfid_number == rfid_number
        )
    )

    if card_active is None:
        return UNKNOWN_CARD, None

    if not card_active:
        return INACTIVE_CARD, None

    return NO_ASSIGNMENT, None


class RFIDIssueCollector:
    """Sammelt nicht zuordenbare RFID-Nummern eines Imports."""

    def __init__(self) -> None:
        self.sessions = 0
        self.numbers: dict[str, set[str]] = {
            UNKNOWN_CARD: set(),
            INACTIVE_CARD: set(),
            NO_ASSIGNMENT: set(),
        }

    def add(self, status: str, rfid_number: str) -> None:
        self.sessions += 1
        self.numbers[status].add(rfid_number)

    def as_result(self) -> dict[str, object]:
        all_numbers = set().union(*self.numbers.values())

        return {
            # bisherige Felder: alle nicht zugeordneten Nummern
            "unknown_rfid_sessions": self.sessions,
            "unknown_rfid_numbers": sorted(all_numbers),
            # aufgeschlüsselt nach Ursache
            "unknown_rfid_cards": sorted(self.numbers[UNKNOWN_CARD]),
            "inactive_rfid_cards": sorted(self.numbers[INACTIVE_CARD]),
            "unassigned_rfid_numbers": sorted(self.numbers[NO_ASSIGNMENT]),
        }


def open_unassigned_sessions_statement():
    return select(ChargingSession).where(
        ChargingSession.rfid_number.is_not(None),
        ChargingSession.rfid_assignment_id.is_(None),
        or_(
            ChargingSession.invoiced.is_(False),
            ChargingSession.invoiced.is_(None),
        ),
        ChargingSession.invoice_id.is_(None),
        ~ChargingSession.invoice_items.any(),
    )


def reassign_open_sessions(db: Session) -> int:
    """
    Verknüpft nicht abgerechnete Ladevorgänge ohne Zuordnung mit der
    zum Ladezeitpunkt gültigen Zuordnung. Kein Commit.

    Rückgabe: Anzahl neu zugeordneter Ladevorgänge.
    """
    reassigned = 0

    for charging_session in db.scalars(
        open_unassigned_sessions_statement()
    ).all():
        status, assignment = classify_rfid(
            db,
            charging_session.rfid_number,
            charging_session.start_time,
        )

        if status == ASSIGNED and assignment is not None:
            charging_session.rfid_card_id = assignment.rfid_card_id
            charging_session.rfid_assignment_id = assignment.id
            reassigned += 1

    if reassigned:
        logger.info(
            "%s Ladevorgänge nachträglich einer RFID-Zuordnung "
            "zugeordnet",
            reassigned,
        )

    return reassigned


def reassign_after_change(db: Session) -> int:
    """
    Nach Änderungen an Karten oder Zuordnungen aufrufen (nach deren
    Commit). Fehler hier dürfen die eigentliche Änderung nicht
    beeinträchtigen.
    """
    try:
        reassigned = reassign_open_sessions(db)

        if reassigned:
            db.commit()

        return reassigned
    except Exception:
        db.rollback()
        logger.exception(
            "Nachträgliche RFID-Zuordnung fehlgeschlagen"
        )
        return 0
