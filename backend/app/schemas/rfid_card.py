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
    note: str | None
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
                "The RFID number must not be empty."
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
                "The RFID number must not be empty."
            )

        normalized = value.strip().upper()

        if not normalized:
            raise ValueError(
                "The RFID number must not be empty."
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
                "The active status must not be empty."
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
    note: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator("note")
    @classmethod
    def normalize_note(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError(
                "The end of the assignment must be after its start."
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
    note: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator("note")
    @classmethod
    def normalize_note(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @model_validator(mode="after")
    def validate_update(self):
        if (
            "user_id" in self.model_fields_set
            and self.user_id is None
        ):
            raise ValueError(
                "The user must not be empty."
            )

        if (
            "valid_from" in self.model_fields_set
            and self.valid_from is None
        ):
            raise ValueError(
                "The start of the assignment must not be empty."
            )

        if (
            self.valid_from is not None
            and "valid_to" in self.model_fields_set
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError(
                "The end of the assignment must be after its start."
            )

        return self
