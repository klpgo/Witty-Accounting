from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.global_settings import GlobalSettings
from app.schemas.hager_settings import (
    HagerConnectionTestResponse,
    HagerSettingsResponse,
    HagerSettingsUpdate,
)
from app.services.hager_secret import encrypt_hager_password
from app.services.hager_sync import (
    HagerConfigurationError,
    HagerConnectionError,
    check_connection,
)
from app.services.hager_schedule import (
    next_slot,
    parse_start_time,
)
from app.services.hager_token_cache import token_cache
from app.services.smtp_secret import SmtpSecretError


router = APIRouter(
    prefix="/settings/hager",
    tags=["settings"],
)


def load_global_settings(db: Session) -> GlobalSettings:
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Die globalen Einstellungen wurden nicht gefunden.",
        )

    return global_settings


def as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None else None


def is_access_complete(global_settings: GlobalSettings) -> bool:
    return bool(
        global_settings.hager_username
        and global_settings.hager_password_encrypted
        and global_settings.hager_installation_id
    )


def build_response(
    global_settings: GlobalSettings,
) -> HagerSettingsResponse:
    next_run_at = None

    if global_settings.hager_auto_import_enabled:
        next_run_at = next_slot(
            datetime.now(UTC),
            parse_start_time(global_settings.hager_auto_import_start_time),
            global_settings.hager_auto_import_interval_hours,
        )

    return HagerSettingsResponse(
        username=global_settings.hager_username,
        installation_id=global_settings.hager_installation_id,
        password_configured=(
            global_settings.hager_password_encrypted is not None
        ),
        auto_import_enabled=global_settings.hager_auto_import_enabled,
        auto_import_interval_hours=(
            global_settings.hager_auto_import_interval_hours
        ),
        auto_import_start_time=global_settings.hager_auto_import_start_time,
        auto_import_next_run_at=next_run_at,
        auto_import_last_started_at=as_utc(
            global_settings.hager_auto_import_last_started_at
        ),
        auto_import_last_finished_at=as_utc(
            global_settings.hager_auto_import_last_finished_at
        ),
        auto_import_last_status=global_settings.hager_auto_import_last_status,
        auto_import_last_message=(
            global_settings.hager_auto_import_last_message
        ),
        last_successful_fetch_at=as_utc(
            global_settings.hager_last_successful_fetch_at
        ),
    )


@router.get(
    "",
    response_model=HagerSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def read_hager_settings(
    db: Session = Depends(get_db),
) -> HagerSettingsResponse:
    return build_response(load_global_settings(db))


@router.patch(
    "",
    response_model=HagerSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_hager_settings(
    data: HagerSettingsUpdate,
    db: Session = Depends(get_db),
) -> HagerSettingsResponse:
    global_settings = load_global_settings(db)
    updates = data.model_dump(
        exclude_unset=True,
        exclude={"password", "clear_password"},
    )
    previous_username = global_settings.hager_username

    if "username" in updates:
        global_settings.hager_username = updates["username"] or None

    if "installation_id" in updates:
        global_settings.hager_installation_id = (
            updates["installation_id"] or None
        )

    if data.auto_import_interval_hours is not None:
        global_settings.hager_auto_import_interval_hours = (
            data.auto_import_interval_hours
        )

    if data.auto_import_start_time is not None:
        global_settings.hager_auto_import_start_time = (
            data.auto_import_start_time
        )

    if data.auto_import_enabled is not None:
        global_settings.hager_auto_import_enabled = (
            data.auto_import_enabled
        )

    if data.clear_password:
        global_settings.hager_password_encrypted = None
    elif data.password is not None:
        password = data.password.get_secret_value()

        if password:
            try:
                global_settings.hager_password_encrypted = (
                    encrypt_hager_password(password)
                )
            except SmtpSecretError as exc:
                raise HTTPException(
                    status_code=(
                        status.HTTP_500_INTERNAL_SERVER_ERROR
                    ),
                    detail=str(exc),
                ) from exc

    if (
        global_settings.hager_auto_import_enabled
        and not is_access_complete(global_settings)
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Für den automatischen Abruf müssen Benutzername, "
                "Passwort und Installations-ID gespeichert sein."
            ),
        )

    try:
        db.commit()
        db.refresh(global_settings)
    except Exception:
        db.rollback()
        raise

    # Zwischengespeicherte Hager-Tokens des bisherigen Zugangs verwerfen
    if previous_username:
        token_cache.invalidate(previous_username)

    return build_response(global_settings)


@router.post(
    "/test",
    response_model=HagerConnectionTestResponse,
    dependencies=[Depends(require_admin)],
)
def test_hager_connection(
    db: Session = Depends(get_db),
) -> HagerConnectionTestResponse:
    """Meldet sich bei Hager flow an und ruft die Sessions ab,
    ohne etwas zu importieren."""
    try:
        result = check_connection(db)
    except HagerConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except HagerConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SmtpSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return HagerConnectionTestResponse(**result)
