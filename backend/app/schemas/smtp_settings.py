from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


SmtpHost = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
    ),
]

SmtpPort = Annotated[
    int,
    Field(
        ge=1,
        le=65535,
    ),
]

SmtpTimeout = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        le=Decimal("300"),
        max_digits=8,
        decimal_places=2,
    ),
]

MailAddress = Annotated[
    str,
    Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]

MailName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
    ),
]

OptionalUsername = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
    ),
]


class SmtpSettingsResponse(BaseModel):
    smtp_use_database_settings: bool
    mail_sending_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_timeout_seconds: Decimal
    smtp_starttls: bool
    smtp_username: str | None
    smtp_password_configured: bool
    mail_from_address: str
    mail_from_name: str
    mail_smime_enabled: bool
    smime_certificate_configured: bool
    smime_certificate_filename: str | None
    smime_certificate_source: str | None
    smime_password_configured: bool

class SmtpTestEmailResponse(BaseModel):
    recipient_email: str
    subject: str

class SmtpSettingsUpdate(BaseModel):
    smtp_use_database_settings: (
        bool | None
    ) = None
    mail_sending_enabled: bool | None = None
    smtp_host: SmtpHost | None = None
    smtp_port: SmtpPort | None = None
    smtp_timeout_seconds: (
        SmtpTimeout | None
    ) = None
    smtp_starttls: bool | None = None
    smtp_username: (
        OptionalUsername | None
    ) = None
    smtp_password: SecretStr | None = None
    clear_smtp_password: bool = False
    mail_from_address: MailAddress | None = None
    mail_from_name: MailName | None = None
    mail_smime_enabled: bool | None = None
    smime_pkcs12_base64: Annotated[
        str,
        Field(
            min_length=1,
            max_length=90000,
        ),
    ] | None = None
    smime_pkcs12_filename: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] | None = None
    smime_password: SecretStr | None = None
    clear_smime_certificate: bool = False

    @field_validator(
        "smtp_use_database_settings",
        "mail_sending_enabled",
        "smtp_host",
        "smtp_port",
        "smtp_timeout_seconds",
        "smtp_starttls",
        "mail_from_address",
        "mail_from_name",
        "mail_smime_enabled",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(
        cls,
        value: object,
    ) -> object:
        if value is None:
            raise ValueError(
                "Der SMTP-Einstellungswert darf "
                "nicht null sein."
            )

        return value

    @field_validator(
        "smtp_host",
        "mail_from_address",
        "mail_from_name",
        mode="before",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        return value.strip()

    @field_validator(
        "smtp_username",
        mode="before",
    )
    @classmethod
    def normalize_optional_username(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = value.strip()

        return normalized or None

    @field_validator(
        "smtp_password",
        "smime_password",
        mode="before",
    )
    @classmethod
    def normalize_password(
        cls,
        value: object,
    ) -> object:
        if value == "":
            return None

        return value

    @model_validator(mode="after")
    def validate_password_operation(
        self,
    ) -> "SmtpSettingsUpdate":
        if (
            self.smtp_password is not None
            and self.clear_smtp_password
        ):
            raise ValueError(
                "Das SMTP-Passwort kann nicht "
                "gleichzeitig gesetzt und gelöscht "
                "werden."
            )

        if (
            self.clear_smime_certificate
            and (
                self.smime_pkcs12_base64 is not None
                or self.smime_password is not None
            )
        ):
            raise ValueError(
                "Das S/MIME-Zertifikat kann nicht "
                "gleichzeitig gesetzt und gelöscht "
                "werden."
            )

        if (
            self.smime_pkcs12_base64 is not None
            and self.smime_pkcs12_filename is None
        ):
            raise ValueError(
                "Zum S/MIME-Zertifikat fehlt der "
                "Dateiname."
            )

        if (
            self.smime_pkcs12_filename is not None
            and self.smime_pkcs12_base64 is None
        ):
            raise ValueError(
                "Ein S/MIME-Dateiname darf nur mit "
                "einem Zertifikat übertragen werden."
            )

        return self
