from dataclasses import dataclass
from email.message import EmailMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.models.global_settings import GlobalSettings
from app.services.smime import (
    SmimeSigningError,
    load_signing_material_from_data,
    read_pkcs12_password,
    sign_message_from_data,
)
from app.services.smtp_secret import (
    SmtpSecretError,
    decrypt_smime_password,
)


class MailSmimeConfigurationError(Exception):
    """Die S/MIME-Konfiguration ist unvollständig."""


@dataclass(frozen=True)
class SmimeMaterial:
    pkcs12_data: bytes
    password: bytes
    filename: str
    source: str


def environment_smime_status(
) -> tuple[bool, bool, str | None]:
    pkcs12_path = settings.mail_smime_pkcs12_path
    password_path = (
        settings.mail_smime_pkcs12_password_file
    )

    certificate_configured = (
        pkcs12_path is not None
        and pkcs12_path.is_file()
    )
    password_configured = (
        password_path is not None
        and password_path.is_file()
    )
    filename = (
        pkcs12_path.name
        if certificate_configured
        and pkcs12_path is not None
        else None
    )

    return (
        certificate_configured,
        password_configured,
        filename,
    )


def _read_environment_material() -> SmimeMaterial:
    pkcs12_path = settings.mail_smime_pkcs12_path
    password_path = (
        settings.mail_smime_pkcs12_password_file
    )

    if pkcs12_path is None:
        raise MailSmimeConfigurationError(
            "Der Pfad zur S/MIME-PKCS#12-Datei "
            "ist nicht konfiguriert."
        )

    if password_path is None:
        raise MailSmimeConfigurationError(
            "Der Pfad zur S/MIME-Passwortdatei "
            "ist nicht konfiguriert."
        )

    try:
        pkcs12_data = pkcs12_path.read_bytes()
    except OSError as exc:
        raise MailSmimeConfigurationError(
            "Die konfigurierte S/MIME-PKCS#12-Datei "
            "konnte nicht gelesen werden."
        ) from exc

    try:
        password = read_pkcs12_password(
            password_path
        )
    except SmimeSigningError as exc:
        raise MailSmimeConfigurationError(
            str(exc)
        ) from exc

    return SmimeMaterial(
        pkcs12_data=pkcs12_data,
        password=password,
        filename=pkcs12_path.name,
        source="environment",
    )


def load_smime_material(
    db: Session,
    *,
    require_enabled: bool = True,
) -> SmimeMaterial | None:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    enabled = (
        global_settings.mail_smime_enabled
        if global_settings is not None
        else settings.mail_smime_enabled
    )

    if require_enabled and not enabled:
        return None

    stored_data = (
        global_settings.mail_smime_pkcs12_data
        if global_settings is not None
        else None
    )
    stored_password = (
        global_settings
        .mail_smime_pkcs12_password_encrypted
        if global_settings is not None
        else None
    )

    if stored_data is not None or stored_password is not None:
        if stored_data is None or stored_password is None:
            raise MailSmimeConfigurationError(
                "Das gespeicherte S/MIME-Zertifikat "
                "und das S/MIME-Passwort sind "
                "unvollständig."
            )

        try:
            password = decrypt_smime_password(
                stored_password
            ).encode("utf-8")
        except SmtpSecretError as exc:
            raise MailSmimeConfigurationError(
                "Das gespeicherte S/MIME-Passwort "
                "konnte nicht verwendet werden."
            ) from exc

        return SmimeMaterial(
            pkcs12_data=stored_data,
            password=password,
            filename=(
                global_settings
                .mail_smime_pkcs12_filename
                or "S/MIME-Zertifikat.p12"
            ),
            source="upload",
        )

    return _read_environment_material()


def validate_smime_material(
    *,
    pkcs12_data: bytes,
    password: str,
    sender_email: str,
) -> None:
    try:
        load_signing_material_from_data(
            pkcs12_data=pkcs12_data,
            password=password.encode("utf-8"),
            sender_email=sender_email,
        )
    except SmimeSigningError as exc:
        raise MailSmimeConfigurationError(
            str(exc)
        ) from exc


def sign_configured_message(
    db: Session,
    *,
    message: EmailMessage,
    sender_email: str,
    require_enabled: bool = True,
) -> bytes | None:
    material = load_smime_material(
        db,
        require_enabled=require_enabled,
    )

    if material is None:
        return None

    try:
        return sign_message_from_data(
            message=message,
            sender_email=sender_email,
            pkcs12_data=material.pkcs12_data,
            password=material.password,
        )
    except SmimeSigningError as exc:
        raise MailSmimeConfigurationError(
            str(exc)
        ) from exc
