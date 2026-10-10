import json
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.billing_run import BillingRun
from app.models.global_settings import GlobalSettings
from app.models.invoice import (
    DELIVERY_FAILED,
    REVIEW_FAILED,
    REVIEW_IN_REVIEW,
    REVIEW_ON_HOLD,
    Invoice,
)
from app.models.user import User
from app.schemas.auto_billing import (
    AutoBillingPreviewCustomer,
    AutoBillingPreviewResponse,
    AutoBillingSettingsResponse,
    AutoBillingSettingsUpdate,
    BillingRunResponse,
    BillingRunSkipped,
)
from app.services.auto_billing import (
    billable_user_ids,
    data_ready,
    local_now,
    local_to_utc,
    overlapping_draft,
    upcoming_period,
)
from app.services.billing_email import notification_address
from app.services.billing_schedule import (
    INTERVAL_WEEKLY,
    run_at,
    validate_schedule,
)
from app.services.hager_schedule import parse_start_time


router = APIRouter(
    prefix="/settings/auto-billing",
    tags=["settings"],
)

RUN_HISTORY_LIMIT = 12


def load_global_settings(db: Session) -> GlobalSettings:
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The global settings were not found.",
        )

    return global_settings


def as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None else None


def _count(db: Session, *conditions: object) -> int:
    return int(
        db.scalar(select(func.count(Invoice.id)).where(*conditions)) or 0
    )


def build_run_response(db: Session, run: BillingRun) -> BillingRunResponse:
    skipped: list[BillingRunSkipped] = []

    try:
        entries = json.loads(run.details or "[]")
    except ValueError:
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        user_id = entry.get("user_id")
        user = db.get(User, user_id) if isinstance(user_id, int) else None

        skipped.append(
            BillingRunSkipped(
                user_id=user_id,
                # Name aktuell nachschlagen; gelöschte Kunden nur mit ID
                name=(
                    f"{user.first_name} {user.last_name}".strip()
                    if user is not None
                    else f"#{user_id}"
                ),
                reason=str(entry.get("reason", "")),
                invoice_id=entry.get("invoice_id"),
                message=entry.get("message"),
            )
        )

    return BillingRunResponse(
        id=run.id,
        period_start=run.period_start,
        period_end=run.period_end,
        cutoff_date=run.cutoff_date,
        interval=run.interval,
        status=run.status,
        review_due_date=run.review_due_date,
        drafts_created=run.drafts_created,
        open_drafts=_count(
            db,
            Invoice.billing_run_id == run.id,
            Invoice.status == "draft",
        ),
        on_hold=_count(
            db,
            Invoice.billing_run_id == run.id,
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_ON_HOLD,
        ),
        skipped=skipped,
        created_at=as_utc(run.created_at),
        drafts_created_at=as_utc(run.drafts_created_at),
        completed_at=as_utc(run.completed_at),
    )


def build_response(
    db: Session,
    global_settings: GlobalSettings,
) -> AutoBillingSettingsResponse:
    response = AutoBillingSettingsResponse(
        enabled=global_settings.auto_billing_enabled,
        interval=global_settings.auto_billing_interval,
        cutoff_day=global_settings.auto_billing_cutoff_day,
        grace_days=global_settings.auto_billing_grace_days,
        review_days=global_settings.auto_billing_review_days,
        run_time=global_settings.auto_billing_run_time,
        notification_email=global_settings.auto_billing_notification_email,
        effective_notification_email=notification_address(db),
        active_since=global_settings.auto_billing_active_since,
        waits_for_hager_fetch=global_settings.hager_auto_import_enabled,
        open_in_review=_count(
            db,
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_IN_REVIEW,
        ),
        open_on_hold=_count(
            db,
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_ON_HOLD,
        ),
        open_failed=_count(
            db,
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_FAILED,
        ),
        delivery_failed=_count(
            db,
            Invoice.status == "finalized",
            Invoice.delivery_status == DELIVERY_FAILED,
        ),
        runs=[
            build_run_response(db, run)
            for run in db.scalars(
                select(BillingRun)
                .order_by(BillingRun.period_start.desc())
                .limit(RUN_HISTORY_LIMIT)
            ).all()
        ],
    )

    if global_settings.auto_billing_enabled:
        period = upcoming_period(
            db,
            global_settings,
            local_now().date(),
        )
        response.next_period_start = period.start
        response.next_period_end = period.end
        response.next_cutoff = period.cutoff
        response.next_run_at = local_to_utc(
            run_at(
                period.cutoff,
                global_settings.auto_billing_grace_days,
                parse_start_time(global_settings.auto_billing_run_time),
            )
        ).replace(tzinfo=UTC)

    return response


@router.get(
    "",
    response_model=AutoBillingSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def read_auto_billing_settings(
    db: Session = Depends(get_db),
) -> AutoBillingSettingsResponse:
    return build_response(db, load_global_settings(db))


@router.patch(
    "",
    response_model=AutoBillingSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_auto_billing_settings(
    data: AutoBillingSettingsUpdate,
    db: Session = Depends(get_db),
) -> AutoBillingSettingsResponse:
    global_settings = load_global_settings(db)
    was_enabled = global_settings.auto_billing_enabled

    interval = (
        data.interval
        if data.interval is not None
        else global_settings.auto_billing_interval
    )
    cutoff_day = (
        data.cutoff_day
        if data.cutoff_day is not None
        else global_settings.auto_billing_cutoff_day
    )

    # Beim Wechsel zwischen wöchentlich und monatlich passt der bisherige
    # Stichtag oft nicht; ohne Angabe gilt dann ein Standard
    if data.interval is not None and data.cutoff_day is None:
        try:
            validate_schedule(interval, cutoff_day)
        except ValueError:
            cutoff_day = 7 if interval == INTERVAL_WEEKLY else 0

    try:
        validate_schedule(interval, cutoff_day)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    global_settings.auto_billing_interval = interval
    global_settings.auto_billing_cutoff_day = cutoff_day

    if data.grace_days is not None:
        global_settings.auto_billing_grace_days = data.grace_days

    if data.review_days is not None:
        global_settings.auto_billing_review_days = data.review_days

    if data.run_time is not None:
        global_settings.auto_billing_run_time = data.run_time

    if data.notification_email is not None:
        global_settings.auto_billing_notification_email = (
            data.notification_email or None
        )

    if data.enabled is not None:
        global_settings.auto_billing_enabled = data.enabled

        if data.enabled and not was_enabled:
            # abgerechnet werden Zeiträume mit Stichtag ab heute
            global_settings.auto_billing_active_since = local_now().date()

    if (
        global_settings.auto_billing_enabled
        and notification_address(db) is None
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Automatic billing needs a notification address or a "
                "configured sender address."
            ),
        )

    try:
        db.commit()
        db.refresh(global_settings)
    except Exception:
        db.rollback()
        raise

    return build_response(db, global_settings)


@router.get(
    "/preview",
    response_model=AutoBillingPreviewResponse,
    dependencies=[Depends(require_admin)],
)
def preview_auto_billing(
    db: Session = Depends(get_db),
) -> AutoBillingPreviewResponse:
    """Probelauf: welcher Zeitraum als Nächstes, für welche Kunden."""
    global_settings = load_global_settings(db)

    try:
        validate_schedule(
            global_settings.auto_billing_interval,
            global_settings.auto_billing_cutoff_day,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    period = upcoming_period(db, global_settings, local_now().date())
    customers: list[AutoBillingPreviewCustomer] = []

    for user_id in billable_user_ids(db, period.start, period.end):
        user = db.get(User, user_id)

        if user is None:
            continue

        existing = overlapping_draft(db, user.id, period.start, period.end)

        if user.invoice_delivery_post and not user.invoice_delivery_email:
            delivery = "post"
        elif user.invoice_delivery_email:
            delivery = "email"
        else:
            delivery = "portal"

        customers.append(
            AutoBillingPreviewCustomer(
                user_id=user.id,
                name=f"{user.first_name} {user.last_name}".strip(),
                email=user.email,
                delivery=delivery,
                has_address=bool((user.address or "").strip()),
                existing_draft_id=(
                    existing.id if existing is not None else None
                ),
            )
        )

    customers.sort(key=lambda customer: customer.name.lower())

    return AutoBillingPreviewResponse(
        period_start=period.start,
        period_end=period.end,
        cutoff_date=period.cutoff,
        run_at=local_to_utc(
            run_at(
                period.cutoff,
                global_settings.auto_billing_grace_days,
                parse_start_time(global_settings.auto_billing_run_time),
            )
        ).replace(tzinfo=UTC),
        data_ready=data_ready(global_settings, period.end),
        customers=customers,
    )
