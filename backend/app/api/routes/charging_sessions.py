from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import get_current_user, require_admin
from app.models.charging_session import ChargingSession
from app.models.invoice import Invoice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.schemas.charging_session import (
    ChargingSessionBulkResult,
    ChargingSessionDiscardRequest,
    ChargingSessionIdsRequest,
    ChargingSessionResponse,
)
from app.services.charging_session_discard import (
    ChargingSessionNotFoundError,
    DiscardNotAllowedError,
    discard_sessions,
    restore_sessions,
)


router = APIRouter(
    prefix="/charging-sessions",
    tags=["charging-sessions"],
)


@router.get(
    "",
    response_model=list[ChargingSessionResponse],
)
def list_charging_sessions(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    include_discarded: bool = False,
) -> list[ChargingSessionResponse]:
    statement = (
        select(
            ChargingSession,
            RFIDCardAssignment.user_id.label(
                "assigned_user_id"
            ),
            User.first_name,
            User.last_name,
            RFIDCard.rfid_number,
            Invoice.invoice_number,
            Invoice.status.label("invoice_status"),
        )
        .outerjoin(
            RFIDCardAssignment,
            ChargingSession.rfid_assignment_id
            == RFIDCardAssignment.id,
        )
        .outerjoin(
            User,
            RFIDCardAssignment.user_id == User.id,
        )
        .outerjoin(
            RFIDCard,
            ChargingSession.rfid_card_id
            == RFIDCard.id,
        )
        .outerjoin(
            Invoice,
            ChargingSession.invoice_id == Invoice.id,
        )
        .order_by(
            ChargingSession.start_time.desc(),
            ChargingSession.id.desc(),
        )
    )

    if not current_user.is_admin:
        statement = statement.where(
            RFIDCardAssignment.user_id
            == current_user.id
        )

    # Verworfene nur für Admins und nur auf Wunsch
    if not (current_user.is_admin and include_discarded):
        statement = statement.where(
            ChargingSession.discarded_at.is_(None)
        )

    rows = db.execute(statement).all()
    result: list[ChargingSessionResponse] = []
    for (
        charging_session,
        assigned_user_id,
        first_name,
        last_name,
        rfid_number,
        invoice_number,
        invoice_status,
    ) in rows:
        invoice_is_readable = (
            current_user.is_admin
            or invoice_status == "finalized"
        )

        result.append(
            ChargingSessionResponse(
                id=charging_session.id,
                user_id=assigned_user_id,
                user_name=(
                    f"{first_name} {last_name}".strip()
                    if first_name is not None
                    and last_name is not None
                    else None
                ),
                # ohne Zuordnung: Nummer aus dem Import (nur für Admins)
                rfid_number=(
                    rfid_number
                    or (
                        charging_session.rfid_number
                        if current_user.is_admin
                        else None
                    )
                ),
                station_id=charging_session.station_id,
                start_time=charging_session.start_time,
                end_time=charging_session.end_time,
                energy_total_kwh=(
                    charging_session.energy_total_kwh
                ),
                energy_pv_kwh=(
                    charging_session.energy_pv_kwh
                ),
                cost_grid_net=(
                    charging_session.cost_grid_net
                ),
                cost_pv_net=(
                    charging_session.cost_pv_net
                ),
                vat_rate=charging_session.vat_rate,
                invoiced=(
                    charging_session.invoiced
                    if current_user.is_admin
                    else invoice_status == "finalized"
                ),
                invoice_id=(
                    charging_session.invoice_id
                    if invoice_is_readable
                    else None
                ),
                invoice_number=(
                    invoice_number
                    if invoice_is_readable
                    else None
                ),
                invoice_status=(
                    invoice_status
                    if invoice_is_readable
                    else None
                ),
                discarded=charging_session.discarded_at is not None,
                discarded_at=charging_session.discarded_at,
                discard_reason=(
                    charging_session.discard_reason
                    if current_user.is_admin
                    else None
                ),
            )
        )

    return result


@router.post(
    "/discard",
    response_model=ChargingSessionBulkResult,
)
def discard_charging_sessions(
    data: ChargingSessionDiscardRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ChargingSessionBulkResult:
    """Verwirft nicht abgerechnete Ladevorgänge (alle oder keiner)."""
    try:
        changed = discard_sessions(
            db,
            data.ids,
            user_id=current_user.id,
            reason=data.reason,
        )
    except ChargingSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DiscardNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ChargingSessionBulkResult(changed=changed)


@router.post(
    "/restore",
    response_model=ChargingSessionBulkResult,
)
def restore_charging_sessions(
    data: ChargingSessionIdsRequest,
    _current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ChargingSessionBulkResult:
    """Hebt das Verwerfen auf."""
    try:
        changed = restore_sessions(db, data.ids)
    except ChargingSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ChargingSessionBulkResult(changed=changed)
