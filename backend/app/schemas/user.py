from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
