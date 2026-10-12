from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceDraftCreate(BaseModel):
    user_id: int = Field(gt=0)
    service_period_start: datetime
    service_period_end: datetime
    # Grundgebühr anteilig für die Tage im Zeitraum statt ganzer Monate,
    # deren Erster im Zeitraum liegt
    prorate_base_fee: bool = False


class InvoiceFinalizeRequest(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None


class InvoiceEmailResponse(BaseModel):
    recipient_email: str
    subject: str


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    item_type: str
    monthly_base_fee_charge_id: int | None
    charging_session_id: int | None
    reversed_invoice_item_id: int | None
    rebills_invoice_item_id: int | None
    position_number: int
    description: str
    session_start: datetime | None
    session_end: datetime | None
    station_id: str | None
    energy_total_kwh: Decimal | None
    energy_grid_kwh: Decimal | None
    energy_pv_kwh: Decimal | None
    grid_price_net: Decimal | None
    pv_price_net: Decimal | None
    cost_grid_net: Decimal | None
    cost_pv_net: Decimal | None
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
    user_id: int | None
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
    pdf_exported_at: datetime | None
    pdf_exported_by_user_id: int | None
    pdf_export_remote_path: str | None

    # ohne Umsatzsteuer erstellt (Kleinunternehmer) und Hinweis dazu
    vat_exempt: bool = False
    vat_exemption_note: str | None = None

    # Automatische Abrechnung
    billing_run_id: int | None = None
    # in_review, on_hold, failed oder None (manueller Entwurf)
    review_status: str | None = None
    review_due_date: date | None = None
    review_notified_at: datetime | None = None
    inquiry_at: datetime | None = None
    # pending, sent, postal, failed (nach automatischer Finalisierung)
    delivery_status: str | None = None
    notification_error: str | None = None
    # Kontaktadresse für Nachfragen zum Entwurf (nur bei Entwürfen zur
    # Prüfung gesetzt)
    review_contact_email: str | None = None

    items: list[InvoiceItemResponse]


class InvoiceInquiryResponse(BaseModel):
    invoice: InvoiceResponse
    contact_email: str | None

