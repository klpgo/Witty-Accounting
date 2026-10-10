import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.billing_schedule import (
    MAX_GRACE_DAYS,
    MAX_REVIEW_DAYS,
    MIN_GRACE_DAYS,
    MIN_REVIEW_DAYS,
)
from app.services.hager_schedule import parse_start_time


BillingInterval = Literal["weekly", "monthly", "quarterly"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BillingRunSkipped(BaseModel):
    user_id: int | None = None
    name: str
    # existing_draft oder error
    reason: str
    invoice_id: int | None = None
    message: str | None = None


class BillingRunResponse(BaseModel):
    id: int
    period_start: datetime
    period_end: datetime
    cutoff_date: date
    interval: str
    # waiting_for_data, in_review, completed
    status: str
    review_due_date: date | None
    drafts_created: int
    open_drafts: int
    on_hold: int
    skipped: list[BillingRunSkipped]
    # Zeitpunkte mit Zeitzone (UTC)
    created_at: datetime
    drafts_created_at: datetime | None
    completed_at: datetime | None


class AutoBillingSettingsResponse(BaseModel):
    enabled: bool
    interval: BillingInterval
    cutoff_day: int
    grace_days: int
    review_days: int
    run_time: str
    notification_email: str | None
    # tatsächlich verwendete Adresse (ersatzweise Absenderadresse)
    effective_notification_email: str | None
    active_since: date | None
    # nächster Leistungszeitraum (Ortszeit, Ende exklusiv) und Zeitpunkt der
    # Entwurfserstellung (UTC); nur wenn eingeschaltet
    next_period_start: datetime | None = None
    next_period_end: datetime | None = None
    next_cutoff: date | None = None
    next_run_at: datetime | None = None
    # Entwürfe warten auf einen erfolgreichen Hager-Abruf
    waits_for_hager_fetch: bool
    open_in_review: int
    open_on_hold: int
    open_failed: int
    delivery_failed: int
    runs: list[BillingRunResponse]


class AutoBillingSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval: BillingInterval | None = None
    cutoff_day: int | None = Field(default=None, ge=0, le=28)
    grace_days: int | None = Field(
        default=None,
        ge=MIN_GRACE_DAYS,
        le=MAX_GRACE_DAYS,
    )
    review_days: int | None = Field(
        default=None,
        ge=MIN_REVIEW_DAYS,
        le=MAX_REVIEW_DAYS,
    )
    run_time: str | None = None
    # leer = Absenderadresse der E-Mails verwenden
    notification_email: str | None = Field(default=None, max_length=320)

    @field_validator("run_time")
    @classmethod
    def validate_run_time(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()
        parse_start_time(value)

        return value

    @field_validator("notification_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()

        if value and not _EMAIL_PATTERN.match(value):
            raise ValueError("The notification address is not a valid email address.")

        return value


class AutoBillingPreviewCustomer(BaseModel):
    user_id: int
    name: str
    email: str
    # email, portal oder post
    delivery: str
    has_address: bool
    # vorhandener Entwurf im Zeitraum: dieser Kunde wird übersprungen
    existing_draft_id: int | None


class AutoBillingPreviewResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    cutoff_date: date
    run_at: datetime
    data_ready: bool
    customers: list[AutoBillingPreviewCustomer]
