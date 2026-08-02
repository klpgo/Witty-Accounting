from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class AuthenticatedUserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    email: str
    first_name: str
    last_name: str
    is_admin: bool
    active: bool


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    email: str = Field(
        max_length=255,
    )

    @field_validator("email")
    @classmethod
    def validate_email(
        cls,
        value: str,
    ) -> str:
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


class PasswordResetRequestResponse(BaseModel):
    message: str


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    token: str = Field(
        min_length=32,
        max_length=512,
    )
    new_password: str = Field(
        min_length=8,
        max_length=1024,
    )
