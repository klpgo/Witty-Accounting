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
