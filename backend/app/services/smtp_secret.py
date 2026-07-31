from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SmtpSecretError(Exception):
    """Base error for encrypted SMTP secrets."""


class SmtpSecretConfigurationError(
    SmtpSecretError
):
    """The encryption key is missing or invalid."""


class SmtpSecretDecryptionError(
    SmtpSecretError
):
    """The stored SMTP secret cannot be decrypted."""


def get_fernet() -> Fernet:
    encryption_key = (
        settings.smtp_settings_encryption_key
    )

    if encryption_key is None:
        raise SmtpSecretConfigurationError(
            "Der Verschlüsselungsschlüssel für "
            "SMTP-Einstellungen ist nicht konfiguriert."
        )

    try:
        return Fernet(
            encryption_key
            .get_secret_value()
            .encode("ascii")
        )
    except (TypeError, ValueError) as exc:
        raise SmtpSecretConfigurationError(
            "Der Verschlüsselungsschlüssel für "
            "SMTP-Einstellungen ist ungültig."
        ) from exc


def encrypt_smtp_password(
    password: str,
) -> str:
    if not password:
        raise SmtpSecretError(
            "Ein leeres SMTP-Passwort kann nicht "
            "verschlüsselt werden."
        )

    encrypted = get_fernet().encrypt(
        password.encode("utf-8")
    )

    return encrypted.decode("ascii")


def decrypt_smtp_password(
    encrypted_password: str,
) -> str:
    try:
        decrypted = get_fernet().decrypt(
            encrypted_password.encode("ascii")
        )
    except (
        InvalidToken,
        UnicodeEncodeError,
        ValueError,
    ) as exc:
        raise SmtpSecretDecryptionError(
            "Das gespeicherte SMTP-Passwort "
            "konnte nicht entschlüsselt werden."
        ) from exc

    return decrypted.decode("utf-8")
