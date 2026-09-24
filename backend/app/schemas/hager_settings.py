from datetime import date, datetime
from typing import Annotated

from app.services.hager_schedule import parse_start_time

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


HagerUsername = Annotated[
    str,
    Field(max_length=320),
]
HagerInstallationId = Annotated[
    str,
    Field(max_length=50),
]


class HagerSettingsResponse(BaseModel):
    username: str | None
    installation_id: str | None
    password_configured: bool
    auto_import_enabled: bool = False
    auto_import_interval_hours: int = 24
    auto_import_start_time: str = "03:00"
    # Zeitpunkte mit Zeitzone (UTC)
    auto_import_next_run_at: datetime | None = None
    auto_import_last_started_at: datetime | None = None
    auto_import_last_finished_at: datetime | None = None
    auto_import_last_status: str | None = None
    auto_import_last_message: str | None = None
    last_successful_fetch_at: datetime | None = None


class HagerSettingsUpdate(BaseModel):
    username: HagerUsername | None = None
    installation_id: HagerInstallationId | None = None
    password: SecretStr | None = None
    clear_password: bool = False
    auto_import_enabled: bool | None = None
    auto_import_interval_hours: int | None = Field(
        default=None,
        ge=1,
        le=24,
    )
    auto_import_start_time: str | None = None

    @field_validator("auto_import_start_time")
    @classmethod
    def validate_start_time(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value

        value = value.strip()
        parse_start_time(value)

        return value

    @field_validator(
        "username",
        "installation_id",
        mode="before",
    )
    @classmethod
    def normalize_text(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        return value.strip()

    @field_validator("installation_id")
    @classmethod
    def validate_installation_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value and not value.isdigit():
            raise ValueError(
                "Die Installations-ID besteht nur "
                "aus Ziffern."
            )

        return value


class HagerConnectionTestResponse(BaseModel):
    sessions: int
    latest_session_start: datetime | None


class HagerImportRequest(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    # vollständiger Abgleich statt Abruf ab dem Cut-off
    fetch_all: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> "HagerImportRequest":
        if self.fetch_all and (
            self.date_from is not None or self.date_to is not None
        ):
            raise ValueError(
                "Beim vollständigen Abruf kann kein Zeitraum "
                "angegeben werden."
            )

        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError(
                "Das Startdatum liegt nach dem Enddatum."
            )

        return self
