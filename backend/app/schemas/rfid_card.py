from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class RFIDCardResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    rfid_number: str
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class RFIDCardAssignmentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    rfid_card_id: int
    user_id: int
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime
    updated_at: datetime


class RFIDCardCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    rfid_number: str = Field(
        min_length=1,
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=255,
    )
    active: bool = True

    @field_validator("rfid_number")
    @classmethod
    def normalize_rfid_number(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().upper()

        if not normalized:
            raise ValueError(
                "Die RFID-Nummer darf nicht "
                "leer sein."
            )

        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None


class RFIDCardUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    rfid_number: str | None = Field(
        default=None,
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=255,
    )
    active: bool | None = None

    @field_validator("rfid_number")
    @classmethod
    def normalize_rfid_number(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError(
                "Die RFID-Nummer darf nicht "
                "leer sein."
            )

        normalized = value.strip().upper()

        if not normalized:
            raise ValueError(
                "Die RFID-Nummer darf nicht "
                "leer sein."
            )

        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @field_validator("active")
    @classmethod
    def validate_active(
        cls,
        value: bool | None,
    ) -> bool:
        if value is None:
            raise ValueError(
                "Der Aktiv-Status darf nicht "
                "leer sein."
            )

        return value


class RFIDCardAssignmentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    user_id: int = Field(
        gt=0,
    )
    valid_from: datetime
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError(
                "Das Ende der Zuordnung muss "
                "nach ihrem Beginn liegen."
            )

        return self


class RFIDCardAssignmentUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    user_id: int | None = Field(
        default=None,
        gt=0,
    )
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if (
            "user_id" in self.model_fields_set
            and self.user_id is None
        ):
            raise ValueError(
                "Der Benutzer darf nicht leer sein."
            )

        if (
            "valid_from" in self.model_fields_set
            and self.valid_from is None
        ):
            raise ValueError(
                "Der Beginn der Zuordnung darf "
                "nicht leer sein."
            )

        if (
            self.valid_from is not None
            and "valid_to" in self.model_fields_set
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError(
                "Das Ende der Zuordnung muss "
                "nach ihrem Beginn liegen."
            )

        return self
