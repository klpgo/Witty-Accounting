from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceDraftCreate(BaseModel):
    user_id: int = Field(gt=0)
    service_period_start: datetime
    service_period_end: datetime


class InvoiceFinalizeRequest(BaseModel):
    issue_date: date | None = None


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    charging_session_id: int
    position_number: int
    description: str
    session_start: datetime
    session_end: datetime
    station_id: str
    energy_total_kwh: Decimal
    energy_grid_kwh: Decimal
    energy_pv_kwh: Decimal
    grid_price_net: Decimal
    pv_price_net: Decimal
    cost_grid_net: Decimal
    cost_pv_net: Decimal
    net_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    gross_amount: Decimal


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    invoice_number: str | None
    user_id: int
    status: str
    issue_date: date | None
    service_period_start: datetime
    service_period_end: datetime
    currency: str
    total_net: Decimal
    vat_amount: Decimal
    total_gross: Decimal
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    items: list[InvoiceItemResponse]
