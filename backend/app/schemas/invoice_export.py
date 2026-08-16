from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


SftpHost = Annotated[
    str,
    Field(min_length=1, max_length=255),
]
SftpPort = Annotated[
    int,
    Field(ge=1, le=65535),
]
SftpUsername = Annotated[
    str,
    Field(min_length=1, max_length=255),
]
SftpDirectory = Annotated[
    str,
    Field(min_length=1, max_length=1024),
]


class InvoiceExportSettingsResponse(BaseModel):
    enabled: bool
    host: str | None
    port: int
    username: str | None
    directory: str | None
    private_key_configured: bool
    known_hosts_configured: bool


class InvoiceExportSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: SftpHost | None = None
    port: SftpPort | None = None
    username: SftpUsername | None = None
    directory: SftpDirectory | None = None

    @field_validator(
        "enabled",
        "host",
        "port",
        "username",
        "directory",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(
        cls,
        value: object,
    ) -> object:
        if value is None:
            raise ValueError(
                "Der SFTP-Einstellungswert darf "
                "nicht null sein."
            )

        return value

    @field_validator(
        "host",
        "username",
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

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if any(
            character.isspace()
            for character in value
        ) or any(
            character in value
            for character in "/@"
        ):
            raise ValueError(
                "Der SFTP-Host muss ein Hostname "
                "oder eine IP-Adresse ohne Schema sein."
            )

        return value

    @field_validator(
        "directory",
        mode="before",
    )
    @classmethod
    def normalize_directory(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()

        if normalized != "/":
            normalized = normalized.rstrip("/")

        return normalized

    @field_validator("directory")
    @classmethod
    def validate_directory(
        cls,
        value: str,
    ) -> str:
        parts = value.split("/")

        if (
            not value.startswith("/")
            or "\x00" in value
            or ".." in parts
        ):
            raise ValueError(
                "Das SFTP-Zielverzeichnis muss ein "
                "absoluter Pfad ohne '..' sein."
            )

        return value

class InvoiceExportTestResponse(BaseModel):
    host: str
    directory: str


class InvoiceExportResponse(BaseModel):
    remote_path: str
    exported_at: datetime
