"""Verschlüsselung des Hager-Cloud-Passworts.

Nutzt denselben Fernet-Schlüssel wie die Mail-Einstellungen
(SMTP_SETTINGS_ENCRYPTION_KEY).
"""
from cryptography.fernet import InvalidToken

from app.services.smtp_secret import (
    SmtpSecretError,
    get_fernet,
)


class HagerSecretError(SmtpSecretError):
    """Fehler beim Ver- oder Entschlüsseln des Hager-Passworts."""


def encrypt_hager_password(password: str) -> str:
    if not password:
        raise HagerSecretError(
            "An empty Hager password cannot be encrypted."
        )

    return (
        get_fernet()
        .encrypt(password.encode("utf-8"))
        .decode("ascii")
    )


def decrypt_hager_password(encrypted_password: str) -> str:
    try:
        decrypted = get_fernet().decrypt(
            encrypted_password.encode("ascii")
        )
    except (
        InvalidToken,
        UnicodeEncodeError,
        ValueError,
    ) as exc:
        raise HagerSecretError(
            "The saved Hager password could not be decrypted."
        ) from exc

    return decrypted.decode("utf-8")
