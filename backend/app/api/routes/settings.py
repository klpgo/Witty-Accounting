import base64
import binascii
from decimal import Decimal
import re
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session
from typing import Annotated

from app.api.dependencies import (
    get_db,
    get_tenant_context,
)
from app.auth import require_admin
from app.config import settings as app_settings
from app.models.global_settings import GlobalSettings
from app.models.user import User
from app.tenancy.context import TenantContext

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
    decrypt_smime_password,
    encrypt_smime_password,
    encrypt_smtp_password,
)
from app.services.mail_smime import (
    MailSmimeConfigurationError,
    environment_smime_status,
    validate_smime_material,
)
from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    InvoiceEmailRecipientError,
    send_smime_test_email,
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
    stored_certificate_configured = (
        global_settings.mail_smime_pkcs12_data
        is not None
    )
    stored_password_configured = (
        global_settings
        .mail_smime_pkcs12_password_encrypted
        is not None
    )

    if (
        stored_certificate_configured
        or stored_password_configured
    ):
        smime_certificate_configured = (
            stored_certificate_configured
        )
        smime_password_configured = (
            stored_password_configured
        )
        smime_certificate_filename = (
            global_settings
            .mail_smime_pkcs12_filename
        )
        smime_certificate_source = "upload"
    else:
        (
            smime_certificate_configured,
            smime_password_configured,
            smime_certificate_filename,
        ) = environment_smime_status()
        smime_certificate_source = (
            "environment"
            if smime_certificate_configured
            or smime_password_configured
            else None
        )

    smime_response_values = {
        "mail_smime_enabled": (
            global_settings.mail_smime_enabled
        ),
        "smime_certificate_configured": (
            smime_certificate_configured
        ),
        "smime_certificate_filename": (
            smime_certificate_filename
        ),
        "smime_certificate_source": (
            smime_certificate_source
        ),
        "smime_password_configured": (
            smime_password_configured
        ),
    }

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
            **smime_response_values,
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
        **smime_response_values,
    )


@router.get(
    "/public",
    response_model=PublicSettingsResponse,
)
def read_public_settings(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(
        get_tenant_context
    ),
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
                tenant_name=tenant.name,
            )

    return PublicSettingsResponse(
        app_name=app_settings.app_name,
        tenant_name=tenant.name,
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
            "smime_pkcs12_base64",
            "smime_pkcs12_filename",
            "smime_password",
            "clear_smime_certificate",
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
                    .HTTP_422_UNPROCESSABLE_CONTENT
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

    smime_data = (
        global_settings.mail_smime_pkcs12_data
    )
    smime_filename = (
        global_settings.mail_smime_pkcs12_filename
    )
    smime_password_encrypted = (
        global_settings
        .mail_smime_pkcs12_password_encrypted
    )
    smime_material_was_updated = False

    if data.clear_smime_certificate:
        smime_data = None
        smime_filename = None
        smime_password_encrypted = None
        smime_material_was_updated = True

    if data.smime_pkcs12_base64 is not None:
        try:
            decoded_certificate = base64.b64decode(
                data.smime_pkcs12_base64,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_CONTENT
                ),
                detail=(
                    "Die hochgeladene S/MIME-Datei "
                    "ist ungültig."
                ),
            ) from exc

        if not decoded_certificate:
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_CONTENT
                ),
                detail=(
                    "Die hochgeladene S/MIME-Datei "
                    "ist leer."
                ),
            )

        if len(decoded_certificate) > 65535:
            raise HTTPException(
                status_code=(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                ),
                detail=(
                    "Die S/MIME-Datei darf höchstens "
                    "65.535 Byte groß sein."
                ),
            )

        raw_filename = (
            data.smime_pkcs12_filename or ""
        ).strip()
        safe_filename = re.split(
            r"[\\/]",
            raw_filename,
        )[-1]

        if not safe_filename.lower().endswith(
            (".p12", ".pfx")
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_CONTENT
                ),
                detail=(
                    "Das S/MIME-Zertifikat muss eine "
                    ".p12- oder .pfx-Datei sein."
                ),
            )

        smime_data = decoded_certificate
        smime_filename = safe_filename
        smime_material_was_updated = True

    smime_plain_password: str | None = None

    if data.smime_password is not None:
        smime_plain_password = (
            data.smime_password.get_secret_value()
        )

        if smime_plain_password:
            try:
                smime_password_encrypted = (
                    encrypt_smime_password(
                        smime_plain_password
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

            smime_material_was_updated = True
    elif smime_password_encrypted is not None:
        try:
            smime_plain_password = (
                decrypt_smime_password(
                    smime_password_encrypted
                )
            )
        except SmtpSecretError as exc:
            raise HTTPException(
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                detail=(
                    "Das gespeicherte S/MIME-Passwort "
                    "konnte nicht verwendet werden."
                ),
            ) from exc

    candidate_smime_enabled = updates.get(
        "mail_smime_enabled",
        global_settings.mail_smime_enabled,
    )
    stored_smime_selected = (
        smime_data is not None
        or smime_password_encrypted is not None
    )

    if stored_smime_selected:
        if (
            smime_data is None
            or smime_plain_password is None
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_CONTENT
                ),
                detail=(
                    "Zum S/MIME-Zertifikat ist ein "
                    "Passwort erforderlich."
                ),
            )

        if (
            smime_material_was_updated
            or candidate_smime_enabled
        ):
            sender_email = (
                str(
                    candidate_values[
                        "Absenderadresse"
                    ]
                )
                if use_database_settings
                else app_settings.mail_from_address
            )

            try:
                validate_smime_material(
                    pkcs12_data=smime_data,
                    password=smime_plain_password,
                    sender_email=sender_email,
                )
            except MailSmimeConfigurationError as exc:
                raise HTTPException(
                    status_code=(
                        status
                        .HTTP_422_UNPROCESSABLE_CONTENT
                    ),
                    detail=str(exc),
                ) from exc
    elif candidate_smime_enabled:
        (
            environment_certificate_configured,
            environment_password_configured,
            _,
        ) = environment_smime_status()

        if not (
            environment_certificate_configured
            and environment_password_configured
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_CONTENT
                ),
                detail=(
                    "Vor dem Aktivieren muss ein "
                    "S/MIME-Zertifikat mit Passwort "
                    "hochgeladen werden."
                ),
            )

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

    if smime_material_was_updated:
        global_settings.mail_smime_pkcs12_data = (
            smime_data
        )
        global_settings.mail_smime_pkcs12_filename = (
            smime_filename
        )
        global_settings.mail_smime_pkcs12_password_encrypted = (
            smime_password_encrypted
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


@router.post(
    "/smtp/smime/test",
    response_model=SmtpTestEmailResponse,
)
def test_smime_settings(
    current_admin: Annotated[
        User,
        Depends(require_admin),
    ],
    db: Session = Depends(get_db),
) -> SmtpTestEmailResponse:
    try:
        result = send_smime_test_email(
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
