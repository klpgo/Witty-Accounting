from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    server_status: Literal[
        "online",
        "maintenance",
    ]
    admin_note: str | None
    latest_charging_session_at: datetime | None
    invoiced_through: datetime | None
    backend_version: str
