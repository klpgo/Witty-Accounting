from decimal import Decimal
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session
from typing import Annotated

from app.api.dependencies import get_db
from app.auth import require_admin
from app.config import settings as app_settings
from app.models.global_settings import GlobalSettings
from app.models.user import User

from app.schemas.settings import (
    GlobalSettingsResponse,
    GlobalSettingsUpdate,
    PublicSettingsResponse,
)
from app.schemas.smtp_settings import (
    SmtpSettingsResponse,
    SmtpSettingsUpdate,
    SmtpTestEmailResponse,
)
from app.services.smtp_secret import (
    SmtpSecretError,
    encrypt_smtp_password,
)
from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    InvoiceEmailRecipientError,
    send_smtp_test_email,
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


def build_smtp_settings_response(
    global_settings: GlobalSettings,
) -> SmtpSettingsResponse:
    if (
        global_settings
        .smtp_use_database_settings
    ):
        required_values = {
            "SMTP-Host": global_settings.smtp_host,
            "SMTP-Port": global_settings.smtp_port,
            "SMTP-Timeout": (
                global_settings.smtp_timeout_seconds
            ),
            "Absenderadresse": (
                global_settings.mail_from_address
            ),
            "Absendername": (
                global_settings.mail_from_name
            ),
        }

        missing_names = [
            name
            for name, value
            in required_values.items()
            if value is None
            or (
                isinstance(value, str)
                and not value.strip()
            )
        ]

        if missing_names:
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_500_INTERNAL_SERVER_ERROR
                ),
                detail=(
                    "Die gespeicherten "
                    "SMTP-Einstellungen sind "
                    "unvollständig: "
                    + ", ".join(missing_names)
                ),
            )

        return SmtpSettingsResponse(
            smtp_use_database_settings=True,
            mail_sending_enabled=(
                global_settings.mail_sending_enabled
            ),
            smtp_host=global_settings.smtp_host,
            smtp_port=global_settings.smtp_port,
            smtp_timeout_seconds=(
                global_settings
                .smtp_timeout_seconds
            ),
            smtp_starttls=bool(
                global_settings.smtp_starttls
            ),
            smtp_username=(
                global_settings.smtp_username
            ),
            smtp_password_configured=(
                global_settings
                .smtp_password_encrypted
                is not None
            ),
            mail_from_address=(
                global_settings.mail_from_address
            ),
            mail_from_name=(
                global_settings.mail_from_name
            ),
        )

    environment_password = (
        app_settings.smtp_password
    )

    return SmtpSettingsResponse(
        smtp_use_database_settings=False,
        mail_sending_enabled=(
            global_settings.mail_sending_enabled
        ),
        smtp_host=app_settings.smtp_host,
        smtp_port=app_settings.smtp_port,
        smtp_timeout_seconds=Decimal(
            str(
                app_settings
                .smtp_timeout_seconds
            )
        ),
        smtp_starttls=(
            app_settings.smtp_starttls
        ),
        smtp_username=(
            app_settings.smtp_username
        ),
        smtp_password_configured=(
            environment_password is not None
            and bool(
                environment_password
                .get_secret_value()
            )
        ),
        mail_from_address=(
            app_settings.mail_from_address
        ),
        mail_from_name=(
            app_settings.mail_from_name
        ),
    )


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

@router.get(
    "/smtp",
    response_model=SmtpSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def read_smtp_settings(
    db: Session = Depends(get_db),
) -> SmtpSettingsResponse:
    global_settings = get_global_settings(db)

    return build_smtp_settings_response(
        global_settings
    )

@router.patch(
    "/smtp",
    response_model=SmtpSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_smtp_settings(
    data: SmtpSettingsUpdate,
    db: Session = Depends(get_db),
) -> SmtpSettingsResponse:
    global_settings = get_global_settings(db)

    updates = data.model_dump(
        exclude_unset=True,
        exclude={
            "smtp_password",
            "clear_smtp_password",
        },
    )

    use_database_settings = updates.get(
        "smtp_use_database_settings",
        global_settings
        .smtp_use_database_settings,
    )

    candidate_values = {
        "SMTP-Host": updates.get(
            "smtp_host",
            global_settings.smtp_host,
        ),
        "SMTP-Port": updates.get(
            "smtp_port",
            global_settings.smtp_port,
        ),
        "SMTP-Timeout": updates.get(
            "smtp_timeout_seconds",
            global_settings
            .smtp_timeout_seconds,
        ),
        "Absenderadresse": updates.get(
            "mail_from_address",
            global_settings
            .mail_from_address,
        ),
        "Absendername": updates.get(
            "mail_from_name",
            global_settings.mail_from_name,
        ),
    }

    if use_database_settings:
        missing_names = [
            name
            for name, value
            in candidate_values.items()
            if value is None
            or (
                isinstance(value, str)
                and not value.strip()
            )
        ]

        if missing_names:
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    "Für datenbankbasierte "
                    "SMTP-Einstellungen fehlen: "
                    + ", ".join(missing_names)
                ),
            )

    password_update: str | None | object = (
        object()
    )
    password_was_updated = False

    if data.clear_smtp_password:
        password_update = None
        password_was_updated = True
    elif data.smtp_password is not None:
        password = (
            data.smtp_password
            .get_secret_value()
        )

        if password:
            try:
                password_update = (
                    encrypt_smtp_password(
                        password
                    )
                )
            except SmtpSecretError as exc:
                raise HTTPException(
                    status_code=(
                        status
                        .HTTP_500_INTERNAL_SERVER_ERROR
                    ),
                    detail=str(exc),
                ) from exc

            password_was_updated = True

    for field_name, value in updates.items():
        setattr(
            global_settings,
            field_name,
            value,
        )

    if password_was_updated:
        global_settings.smtp_password_encrypted = (
            password_update
            if isinstance(
                password_update,
                str,
            )
            else None
        )

    try:
        db.commit()
        db.refresh(global_settings)
    except Exception:
        db.rollback()
        raise

    return build_smtp_settings_response(
        global_settings
    )

@router.post(
    "/smtp/test",
    response_model=SmtpTestEmailResponse,
)
def test_smtp_settings(
    current_admin: Annotated[
        User,
        Depends(require_admin),
    ],
    db: Session = Depends(get_db),
) -> SmtpTestEmailResponse:
    try:
        result = send_smtp_test_email(
            db,
            recipient_email=current_admin.email,
        )
    except (
        InvoiceEmailConfigurationError,
        InvoiceEmailRecipientError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(exc),
        ) from exc
    except InvoiceEmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return SmtpTestEmailResponse(
        recipient_email=result.recipient_email,
        subject=result.subject,
    )

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
