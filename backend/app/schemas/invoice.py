from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceDraftCreate(BaseModel):
    user_id: int = Field(gt=0)
    service_period_start: datetime
    service_period_end: datetime


class InvoiceFinalizeRequest(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    charging_session_id: int | None
    reversed_invoice_item_id: int | None
    rebills_invoice_item_id: int | None
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

class InvoiceCancellationCreate(BaseModel):
    reason: str = Field(
        min_length=1,
        max_length=500,
    )

class InvoiceCancellationFinalize(BaseModel):
    issue_date: date

class InvoiceResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    invoice_number: str | None
    document_type: str
    original_invoice_id: int | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    user_id: int
    recipient_name: str
    recipient_address: str
    status: str
    issue_date: date | None
    due_date: date | None
    service_period_start: datetime
    service_period_end: datetime
    currency: str
    total_net: Decimal
    vat_amount: Decimal
    total_gross: Decimal
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    pdf_storage_path: str | None
    pdf_sha256: str | None
    pdf_size_bytes: int | None
    pdf_created_at: datetime | None

    items: list[InvoiceItemResponse]


