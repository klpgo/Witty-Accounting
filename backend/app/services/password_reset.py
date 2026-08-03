from datetime import timedelta
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from hashlib import sha256
import random
import secrets
from typing import Literal
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.global_settings import GlobalSettings
from app.models.password_reset_token import (
    PasswordResetToken,
)
from app.models.user import User
from app.security import hash_password
from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    deliver_email_message,
    load_smtp_configuration,
)
from app.services.password_policy import (
    PasswordPolicy,
    load_password_policy,
    validate_password,
)
from app.services.smime import (
    SmimeSigningError,
    sign_message,
)
from app.utils.utc import utc_now


PasswordResetPurpose = Literal[
    "password_reset",
    "invitation",
]


@dataclass(frozen=True)
class PasswordResetConfiguration:
    frontend_base_url: str
    expire_minutes: int


class PasswordResetError(Exception):
    """Base class for password-reset failures."""


class InvalidPasswordResetTokenError(
    PasswordResetError
):
    """The supplied token is invalid or expired."""


class PasswordResetEmailError(PasswordResetError):
    """The password-reset email could not be sent."""


def hash_reset_token(token: str) -> str:
    return sha256(
        token.encode("utf-8")
    ).hexdigest()


def load_password_reset_configuration(
    db: Session,
) -> PasswordResetConfiguration:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    if global_settings is not None:
        return PasswordResetConfiguration(
            frontend_base_url=(
                global_settings.frontend_base_url
            ),
            expire_minutes=(
                global_settings
                .password_reset_token_expire_minutes
            ),
        )

    return PasswordResetConfiguration(
        frontend_base_url=settings.frontend_base_url,
        expire_minutes=(
            settings.password_reset_token_expire_minutes
        ),
    )


def create_password_reset_token(
    db: Session,
    *,
    user: User,
    configuration: (
        PasswordResetConfiguration | None
    ) = None,
) -> str:
    now = utc_now()
    effective_configuration = (
        configuration
        or load_password_reset_configuration(db)
    )

    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    token = secrets.token_urlsafe(32)

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(token),
            expires_at=(
                now
                + timedelta(
                    minutes=(
                        effective_configuration
                        .expire_minutes
                    )
                )
            ),
            created_at=now,
        )
    )
    db.flush()

    return token


def get_application_name(db: Session) -> str:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    if global_settings is not None:
        app_name = global_settings.app_name.strip()

        if app_name:
            return app_name

    return settings.app_name


def build_password_reset_url(
    token: str,
    *,
    frontend_base_url: str | None = None,
) -> str:
    base_url = (
        frontend_base_url
        or settings.frontend_base_url
    ).rstrip("/")
    query = urlencode({"token": token})

    return f"{base_url}/reset-password?{query}"


def build_password_reset_message(
    *,
    user: User,
    token: str,
    purpose: PasswordResetPurpose,
    application_name: str,
    sender_email: str,
    sender_name: str,
    configuration: (
        PasswordResetConfiguration | None
    ) = None,
) -> EmailMessage:
    effective_configuration = (
        configuration
        or PasswordResetConfiguration(
            frontend_base_url=(
                settings.frontend_base_url
            ),
            expire_minutes=(
                settings
                .password_reset_token_expire_minutes
            ),
        )
    )
    reset_url = build_password_reset_url(
        token,
        frontend_base_url=(
            effective_configuration.frontend_base_url
        ),
    )
    display_name = (
        f"{user.first_name} {user.last_name}"
    ).strip()
    greeting = (
        f"Guten Tag {display_name},"
        if display_name
        else "Guten Tag,"
    )

    if purpose == "invitation":
        subject = (
            f"Ihr Zugang zu {application_name}"
        )
        introduction = (
            f"für Sie wurde ein Benutzerkonto bei "
            f"{application_name} angelegt. Legen Sie "
            "über den folgenden Link Ihr persönliches "
            "Passwort fest:"
        )
    else:
        subject = (
            f"Passwort für {application_name} zurücksetzen"
        )
        introduction = (
            "über den folgenden Link können Sie ein "
            "neues Passwort festlegen:"
        )

    message = EmailMessage()
    message["From"] = formataddr(
        (
            sender_name,
            sender_email,
        )
    )
    message["To"] = user.email.strip()
    message["Subject"] = subject
    message.set_content(
        f"{greeting}\n\n"
        f"{introduction}\n\n"
        f"{reset_url}\n\n"
        "Der Link ist einmalig und "
        f"{effective_configuration.expire_minutes} "
        "Minuten gültig. Falls Sie diese Nachricht "
        "nicht angefordert haben, können Sie sie "
        "ignorieren.\n\n"
        "Mit freundlichen Grüßen\n"
        f"{sender_name}\n",
        subtype="plain",
        charset="utf-8",
    )

    return message


def sign_password_reset_message(
    *,
    message: EmailMessage,
    sender_email: str,
) -> bytes | None:
    if not settings.mail_smime_enabled:
        return None

    pkcs12_path = settings.mail_smime_pkcs12_path
    password_file = (
        settings.mail_smime_pkcs12_password_file
    )

    if pkcs12_path is None or password_file is None:
        raise PasswordResetEmailError(
            "Die S/MIME-Signatur ist nicht vollständig "
            "konfiguriert."
        )

    try:
        return sign_message(
            message=message,
            sender_email=sender_email,
            pkcs12_path=pkcs12_path,
            password_file=password_file,
        )
    except SmimeSigningError as exc:
        raise PasswordResetEmailError(
            "Die E-Mail konnte nicht mit S/MIME "
            "signiert werden."
        ) from exc


def send_password_reset_email(
    db: Session,
    *,
    user: User,
    token: str,
    purpose: PasswordResetPurpose,
    configuration: (
        PasswordResetConfiguration | None
    ) = None,
) -> None:
    effective_configuration = (
        configuration
        or load_password_reset_configuration(db)
    )
    try:
        smtp_configuration = (
            load_smtp_configuration(db)
        )
    except InvoiceEmailConfigurationError as exc:
        raise PasswordResetEmailError(str(exc)) from exc

    message = build_password_reset_message(
        user=user,
        token=token,
        purpose=purpose,
        application_name=get_application_name(db),
        sender_email=(
            smtp_configuration.from_address
        ),
        sender_name=smtp_configuration.from_name,
        configuration=effective_configuration,
    )

    signed_message = sign_password_reset_message(
        message=message,
        sender_email=(
            smtp_configuration.from_address
        ),
    )

    try:
        deliver_email_message(
            smtp_configuration,
            message=message,
            recipient_email=user.email.strip(),
            signed_message=signed_message,
            delivery_error_message=(
                "Die Passwort-E-Mail konnte nicht "
                "versendet werden."
            ),
        )
    except InvoiceEmailDeliveryError as exc:
        raise PasswordResetEmailError(str(exc)) from exc


def issue_password_reset(
    db: Session,
    *,
    user: User,
    purpose: PasswordResetPurpose,
) -> None:
    configuration = (
        load_password_reset_configuration(db)
    )
    token = create_password_reset_token(
        db,
        user=user,
        configuration=configuration,
    )
    send_password_reset_email(
        db,
        user=user,
        token=token,
        purpose=purpose,
        configuration=configuration,
    )


def reset_password_with_token(
    db: Session,
    *,
    token: str,
    new_password: str,
) -> User:
    now = utc_now()

    reset_token = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash
            == hash_reset_token(token),
            PasswordResetToken.used_at.is_(None),
        )
        .with_for_update()
    )

    if (
        reset_token is None
        or reset_token.expires_at <= now
    ):
        raise InvalidPasswordResetTokenError

    user = db.get(
        User,
        reset_token.user_id,
    )

    if user is None:
        raise InvalidPasswordResetTokenError

    validate_password(
        new_password,
        load_password_policy(db),
    )

    user.password_hash = hash_password(new_password)

    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    return user


def generate_temporary_password(
    policy: PasswordPolicy,
) -> str:
    lowercase = "abcdefghijkmnopqrstuvwxyz"
    uppercase = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digits = "23456789"
    special = "!@#$%&*+-_="
    alphabet = lowercase + uppercase + digits + special

    characters: list[str] = []

    if policy.require_lowercase:
        characters.append(secrets.choice(lowercase))
    if policy.require_uppercase:
        characters.append(secrets.choice(uppercase))
    if policy.require_digit:
        characters.append(secrets.choice(digits))
    if policy.require_special:
        characters.append(secrets.choice(special))

    target_length = max(
        policy.min_length,
        32,
        len(characters),
    )
    characters.extend(
        secrets.choice(alphabet)
        for _ in range(
            target_length - len(characters)
        )
    )

    random.SystemRandom().shuffle(characters)

    return "".join(characters)
