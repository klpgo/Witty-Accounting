from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.config import settings as app_settings
from app.models.global_settings import GlobalSettings
from app.schemas.settings import (
    GlobalSettingsResponse,
    GlobalSettingsUpdate,
    PublicSettingsResponse,
)


router = APIRouter(
    prefix="/settings",
    tags=["settings"],
)


def get_global_settings(
    db: Session,
) -> GlobalSettings:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    if global_settings is None:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Die globalen Einstellungen wurden "
                "nicht gefunden."
            ),
        )

    return global_settings


@router.get(
    "/public",
    response_model=PublicSettingsResponse,
)
def read_public_settings(
    db: Session = Depends(get_db),
) -> PublicSettingsResponse:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    if global_settings is not None:
        app_name = global_settings.app_name.strip()

        if app_name:
            return PublicSettingsResponse(
                app_name=app_name,
            )

    return PublicSettingsResponse(
        app_name=app_settings.app_name,
    )


@router.get(
    "",
    response_model=GlobalSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def read_global_settings(
    db: Session = Depends(get_db),
) -> GlobalSettings:
    return get_global_settings(db)


@router.patch(
    "",
    response_model=GlobalSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_global_settings(
    data: GlobalSettingsUpdate,
    db: Session = Depends(get_db),
) -> GlobalSettings:
    global_settings = get_global_settings(db)

    updates = data.model_dump(
        exclude_unset=True,
    )

    for field_name, value in updates.items():
        setattr(
            global_settings,
            field_name,
            value,
        )

    try:
        db.commit()
        db.refresh(global_settings)
    except Exception:
        db.rollback()
        raise

    return global_settings
