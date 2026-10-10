from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RetentionBlockerResponse(BaseModel):
    code: str
    count: int
    message: str


class RetentionYearResponse(BaseModel):
    year: int
    invoices: int
    cancellations: int
    pdf_files: int
    first_invoice_number: str | None
    last_invoice_number: str | None
    purgeable: bool
    blockers: list[RetentionBlockerResponse]


class RetentionProtocolEntry(BaseModel):
    id: int
    year: int
    retention_years: int
    invoices: int
    cancellations: int
    first_invoice_number: str | None
    last_invoice_number: str | None
    pdf_files: int
    charging_sessions: int
    base_fees: int
    pdf_errors: list[str]
    purged_by: str | None
    purged_at: datetime


class RetentionOverviewResponse(BaseModel):
    retention_years: int
    min_retention_years: int
    max_retention_years: int
    last_purgeable_year: int
    purged_through_year: int | None
    years: list[RetentionYearResponse]
    protocol: list[RetentionProtocolEntry]


class RetentionSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_years: int


class RetentionPurgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_year: int


class RetentionPurgeResponse(BaseModel):
    year: int
    invoices: int
    cancellations: int
    pdf_files: int
    charging_sessions: int
    base_fees: int
    pdf_errors: list[str]
    protocol_id: int


class RetentionDueResponse(BaseModel):
    year: int | None
