"""
Gelöschte Ladevorgänge beim Import wiedererkennen.

Nach dem Löschen eines Benutzers stehen die Merkmale seiner Ladevorgänge
in deleted_charging_sessions. Import und Hager-Abgleich überspringen
solche Ladevorgänge, statt sie erneut anzulegen.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deleted_charging_session import (
    DeletedChargingSession,
)


def find_deleted_session(
    db: Session,
    *,
    start_time: datetime,
    import_hash: str | None = None,
    hager_session_id: str | None = None,
    wallbox_id: str | None = None,
    station_aliases: set[str] | None = None,
) -> DeletedChargingSession | None:
    """
    Prüft, ob ein zu importierender Ladevorgang zu einem gelöschten gehört
    (gleiche Merkmale wie die Dublettenprüfung beim Import).
    """
    if hager_session_id:
        match = db.scalar(
            select(DeletedChargingSession).where(
                DeletedChargingSession.hager_session_id
                == hager_session_id
            )
        )

        if match is not None:
            return match

    if import_hash:
        match = db.scalar(
            select(DeletedChargingSession).where(
                DeletedChargingSession.import_hash == import_hash
            )
        )

        if match is not None:
            return match

    if not wallbox_id and not station_aliases:
        return None

    candidates = db.scalars(
        select(DeletedChargingSession).where(
            DeletedChargingSession.start_time == start_time
        )
    ).all()

    for candidate in candidates:
        if wallbox_id and candidate.wallbox_id == wallbox_id:
            return candidate

        if (
            station_aliases
            and candidate.station_id in station_aliases
        ):
            return candidate

    return None
