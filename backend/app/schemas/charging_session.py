from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ChargingSessionResponse(BaseModel):
    id: int
    user_id: int | None
    user_name: str | None
    rfid_number: str | None
    station_id: str
    start_time: datetime
    end_time: datetime
    energy_total_kwh: float
    energy_pv_kwh: float
    cost_grid_net: Decimal | None
    cost_pv_net: Decimal | None
    vat_rate: Decimal | None
    invoiced: bool
    invoice_id: int | None
    invoice_number: str | None
    invoice_status: str | None
    discarded: bool = False
    discarded_at: datetime | None = None
    discard_reason: str | None = None


class ChargingSessionIdsRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)


class ChargingSessionDiscardRequest(ChargingSessionIdsRequest):
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ChargingSessionBulkResult(BaseModel):
    changed: int
