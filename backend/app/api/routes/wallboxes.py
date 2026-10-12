from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.charging_session import ChargingSession
from app.models.wallbox import Wallbox
from app.schemas.wallbox import WallboxResponse, WallboxUpdate, WallboxUpdateResult
from app.services.wallboxes import apply_name_to_open_sessions, display_name

router = APIRouter(
    prefix="/wallboxes",
    tags=["wallboxes"],
    dependencies=[Depends(require_admin)],
)


def session_statistics(db: Session) -> dict[str, tuple[int, object]]:
    rows = db.execute(
        select(
            ChargingSession.wallbox_id,
            func.count(ChargingSession.id),
            func.max(ChargingSession.start_time),
        )
        .where(ChargingSession.wallbox_id.is_not(None))
        .group_by(ChargingSession.wallbox_id)
    ).all()

    return {wallbox_id: (count, last) for wallbox_id, count, last in rows}


def to_response(wallbox: Wallbox, statistics: dict) -> dict:
    count, last = statistics.get(wallbox.wallbox_id, (0, None))

    return {
        "id": wallbox.id,
        "wallbox_id": wallbox.wallbox_id,
        "hager_name": wallbox.hager_name,
        "custom_name": wallbox.custom_name,
        "display_name": display_name(wallbox),
        "session_count": count,
        "last_session_at": last,
    }


@router.get("", response_model=list[WallboxResponse])
def list_wallboxes(
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Alle Wallboxen mit Namen und Nutzung, zuletzt genutzte zuerst."""
    statistics = session_statistics(db)
    wallboxes = list(db.scalars(select(Wallbox)))
    wallboxes.sort(
        key=lambda wallbox: str(
            statistics.get(wallbox.wallbox_id, (0, None))[1] or ""
        ),
        reverse=True,
    )

    return [to_response(wallbox, statistics) for wallbox in wallboxes]


@router.patch("/{wallbox_pk}", response_model=WallboxUpdateResult)
def update_wallbox(
    wallbox_pk: int,
    data: WallboxUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """
    Setzt den eigenen Namen. Alle noch nicht abgerechneten Ladevorgänge der
    Wallbox übernehmen den angezeigten Namen; abgerechnete bleiben unverändert.
    """
    wallbox = db.get(Wallbox, wallbox_pk)

    if wallbox is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallbox {wallbox_pk} was not found.",
        )

    wallbox.custom_name = data.custom_name
    db.flush()
    updated_sessions = apply_name_to_open_sessions(db, wallbox)
    db.commit()
    db.refresh(wallbox)

    return {
        **to_response(wallbox, session_statistics(db)),
        "updated_sessions": updated_sessions,
    }
