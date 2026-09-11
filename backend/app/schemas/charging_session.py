from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
