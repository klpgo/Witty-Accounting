from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import get_current_user
from app.models.charging_session import (
    ChargingSession,
)
from app.models.global_settings import GlobalSettings
from app.schemas.dashboard import DashboardResponse
from app.version import BACKEND_VERSION


router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get(
    "",
    response_model=DashboardResponse,
    dependencies=[Depends(get_current_user)],
)
def read_dashboard(
    db: Session = Depends(get_db),
) -> DashboardResponse:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    maintenance_mode = (
        global_settings is not None
        and global_settings.maintenance_mode
    )

    latest_charging_session_at = db.scalar(
        select(
            func.max(ChargingSession.end_time)
        )
    )

    invoiced_through = db.scalar(
        select(
            func.max(ChargingSession.end_time)
        ).where(
            ChargingSession.invoiced.is_(True)
        )
    )

    return DashboardResponse(
        server_status=(
            "maintenance"
            if maintenance_mode
            else "online"
        ),
        admin_note=(
            global_settings.dashboard_note
            if global_settings is not None
            else None
        ),
        latest_charging_session_at=(
            latest_charging_session_at
        ),
        invoiced_through=invoiced_through,
        backend_version=BACKEND_VERSION,
    )
