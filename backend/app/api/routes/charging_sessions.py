from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import get_current_user
from app.models.charging_session import ChargingSession
from app.models.invoice import Invoice
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.schemas.charging_session import (
    ChargingSessionResponse,
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
) -> list[ChargingSessionResponse]:
    statement = (
        select(
            ChargingSession,
            RFIDCardAssignment.user_id.label(
                "assigned_user_id"
            ),
            User.first_name,
            User.last_name,
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

    rows = db.execute(statement).all()
    result: list[ChargingSessionResponse] = []
    for (
        charging_session,
        assigned_user_id,
        first_name,
        last_name,
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
            )
        )

    return result
