from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)


class RFIDAssignmentOverlapError(RuntimeError):
    """Mehrere Zuordnungen gelten gleichzeitig."""


def resolve_rfid_assignment(
    db: Session,
    *,
    rfid_number: str,
    at: datetime,
) -> RFIDCardAssignment | None:
    assignments = list(
        db.scalars(
            select(RFIDCardAssignment)
            .join(
                RFIDCard,
                RFIDCardAssignment.rfid_card_id
                == RFIDCard.id,
            )
            .where(
                RFIDCard.rfid_number
                == rfid_number,
                RFIDCard.active.is_(True),
                RFIDCardAssignment.valid_from
                <= at,
                or_(
                    RFIDCardAssignment.valid_to
                    .is_(None),
                    at
                    < RFIDCardAssignment.valid_to,
                ),
            )
            .order_by(
                RFIDCardAssignment.valid_from
                .desc(),
                RFIDCardAssignment.id.desc(),
            )
            .limit(2)
        ).all()
    )

    if len(assignments) > 1:
        raise RFIDAssignmentOverlapError(
            "Für die RFID-Karte "
            f"{rfid_number} gelten zum Zeitpunkt "
            f"{at.isoformat()} mehrere "
            "Benutzerzuordnungen."
        )

    if not assignments:
        return None

    return assignments[0]


def ensure_rfid_assignment_period_available(
    db: Session,
    *,
    rfid_card_id: int,
    valid_from: datetime,
    valid_to: datetime | None,
    current_assignment_id: int | None = None,
) -> None:
    statement = select(
        RFIDCardAssignment.id
    ).where(
        RFIDCardAssignment.rfid_card_id
        == rfid_card_id,
        or_(
            RFIDCardAssignment.valid_to.is_(None),
            RFIDCardAssignment.valid_to
            > valid_from,
        ),
    )

    if valid_to is not None:
        statement = statement.where(
            RFIDCardAssignment.valid_from
            < valid_to
        )

    if current_assignment_id is not None:
        statement = statement.where(
            RFIDCardAssignment.id
            != current_assignment_id
        )

    existing_assignment_id = db.scalar(
        statement.limit(1)
    )

    if existing_assignment_id is not None:
        raise RFIDAssignmentOverlapError(
            "Der Zuordnungszeitraum "
            "überschneidet sich mit einer "
            "bestehenden Zuordnung dieser "
            "RFID-Karte."
        )
