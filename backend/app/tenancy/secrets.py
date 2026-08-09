from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr


class TenantSecretError(RuntimeError):
    """Base error for tenant database secrets."""


class TenantSecretConfigurationError(
    TenantSecretError
):
    """The tenant encryption key is missing or invalid."""


class TenantSecretDecryptionError(
    TenantSecretError
):
    """A stored tenant secret cannot be decrypted."""


def get_fernet(
    encryption_key: SecretStr | None,
) -> Fernet:
    if encryption_key is None:
        raise TenantSecretConfigurationError(
            "TENANT_DB_ENCRYPTION_KEY ist nicht "
            "konfiguriert."
        )

    try:
        return Fernet(
            encryption_key
            .get_secret_value()
            .encode("ascii")
        )
    except (TypeError, ValueError) as exc:
        raise TenantSecretConfigurationError(
            "TENANT_DB_ENCRYPTION_KEY ist "
            "ungültig."
        ) from exc


def encrypt_tenant_db_password(
    password: str,
    *,
    encryption_key: SecretStr | None,
) -> str:
    if not password:
        raise TenantSecretError(
            "Ein leeres Mandanten-DB-Passwort kann "
            "nicht verschlüsselt werden."
        )

    return (
        get_fernet(encryption_key)
        .encrypt(password.encode("utf-8"))
        .decode("ascii")
    )


def decrypt_tenant_db_password(
    encrypted_password: str,
    *,
    encryption_key: SecretStr | None,
) -> str:
    try:
        decrypted = get_fernet(
            encryption_key
        ).decrypt(
            encrypted_password.encode("ascii")
        )
    except (
        InvalidToken,
        UnicodeEncodeError,
        ValueError,
    ) as exc:
        raise TenantSecretDecryptionError(
            "Das Mandanten-DB-Passwort konnte "
            "nicht entschlüsselt werden."
        ) from exc

    return decrypted.decode("utf-8")
