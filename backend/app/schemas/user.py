from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    email: str
    salutation: str | None
    first_name: str
    last_name: str
    address: str | None
    phone: str | None
    invoice_delivery_email: bool
    invoice_delivery_post: bool
    active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    email: str | None = Field(
        default=None,
        max_length=255,
    )
    first_name: str | None = Field(
        default=None,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        max_length=100,
    )
    address: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator(
        "first_name",
        "last_name",
    )
    @classmethod
    def validate_required_name(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError(
                "Der Wert darf nicht leer sein."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Der Wert darf nicht leer sein."
            )

        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError(
                "Die E-Mail-Adresse darf nicht "
                "leer sein."
            )

        normalized = value.strip().lower()

        if (
            not normalized
            or "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError(
                "Die E-Mail-Adresse ist ungültig."
            )

        return normalized

    @field_validator("address")
    @classmethod
    def normalize_address(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None


class UserPasswordChange(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    current_password: str = Field(
        min_length=1,
        max_length=1024,
    )
    new_password: str = Field(
        min_length=8,
        max_length=1024,
    )


class UserAdminUpdate(UserProfileUpdate):
    invoice_delivery_email: bool | None = None
    invoice_delivery_post: bool | None = None
    active: bool | None = None
    is_admin: bool | None = None

    @field_validator(
        "invoice_delivery_email",
        "invoice_delivery_post",
        "active",
        "is_admin",
    )
    @classmethod
    def validate_admin_flag(
        cls,
        value: bool | None,
    ) -> bool:
        if value is None:
            raise ValueError(
                "Der Wert darf nicht leer sein."
            )

        return value


class UserPasswordReset(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    new_password: str = Field(
        min_length=8,
        max_length=1024,
    )
