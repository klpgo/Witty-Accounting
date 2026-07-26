from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
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
