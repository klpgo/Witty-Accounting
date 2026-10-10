"""
Automatische Abrechnung pro Mandant.

Ablauf (siehe docs/admin-guide.md, Abschnitt "Automatische Abrechnung"):

1. Ist der Erstellungszeitpunkt eines Leistungszeitraums erreicht (Stichtag
   + Puffertage, eingestellte Uhrzeit), wird ein Abrechnungslauf angelegt.
   Der Leistungszeitraum ist in der Datenbank eindeutig, ein Zeitraum wird
   also nie doppelt abgerechnet.
2. Ist der automatische Hager-Abruf eingeschaltet, werden die Entwürfe erst
   erstellt, wenn ein erfolgreicher Abruf bis zum Ende des Zeitraums
   vorliegt. Bis dahin wartet der Lauf; der Rechnungssteller wird einmal
   benachrichtigt.
3. Für jeden Kunden mit einer Kartenzuordnung im Zeitraum wird eine
   Sammelrechnung als Entwurf erstellt (create_invoice_draft) und der Kunde
   per E-Mail zur Prüfung im Portal aufgefordert.
4. Nach Ablauf der Prüffrist werden die Entwürfe finalisiert (Nummer,
   Rechnungsdatum und Fälligkeit erst jetzt), archiviert und zugestellt.
   Entwürfe mit Nachfrage des Kunden ("on_hold") bleiben liegen, bis ein
   Administrator sie finalisiert.

Der Scheduler-Heartbeat ruft jede Minute check_all_tenants() auf; jeder
Mandant wird höchstens alle CHECK_INTERVAL geprüft. Die Arbeit läuft in
einem eigenen Hintergrund-Thread, Fehler eines Mandanten beeinträchtigen die
anderen nicht.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.i18n import normalize_language, translate
from app.models.billing_run import (
    RUN_COMPLETED,
    RUN_IN_REVIEW,
    RUN_WAITING_FOR_DATA,
    BillingRun,
)
from app.models.global_settings import GlobalSettings
from app.models.invoice import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_POSTAL,
    DELIVERY_SENT,
    REVIEW_FAILED,
    REVIEW_IN_REVIEW,
    REVIEW_ON_HOLD,
    Invoice,
)
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services import billing_email
from app.services.billing_email import SummaryEntry
from app.services.billing_schedule import (
    BillingPeriod,
    next_period,
    run_at,
)
from app.services.hager_schedule import parse_start_time
from app.services.invoice_archive import (
    InvoiceArchiveError,
    archive_invoice_pdf,
)
from app.services.invoice_email import (
    InvoiceEmailError,
    send_invoice_email,
)
from app.services.invoice_pdf import InvoicePdfError
from app.services.invoicing import (
    InvoiceDraftError,
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
)
from app.services.smtp_secret import SmtpSecretError
from app.tenancy.context import TenantContext
from app.utils.local_time import LOCAL_TIMEZONE
from app.utils.utc import utc_now


logger = logging.getLogger(__name__)

CHECK_INTERVAL = timedelta(minutes=10)
MAX_NOTIFICATION_ATTEMPTS = 5
_ERROR_LENGTH = 500

SessionFactory = Callable[[TenantContext], Session]
Submit = Callable[..., object]

_last_checks: dict[int, datetime] = {}
_running_tenants: set[int] = set()
_state_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

# Fehler, die beim Versand erwartet werden und gemeldet, aber nicht als
# Programmfehler protokolliert werden
MAIL_ERRORS = (InvoiceEmailError, SmtpSecretError)


class InquiryNotFoundError(Exception):
    """Der Entwurf existiert nicht oder gehört nicht zum Kunden."""


class InquiryStateError(Exception):
    """Für den Entwurf ist keine Nachfrage (mehr) möglich."""


# --- Hilfen ----------------------------------------------------------------


def _short(message: object) -> str:
    return str(message)[:_ERROR_LENGTH]


def _customer_label(invoice: Invoice) -> str:
    return f"#{invoice.id} {invoice.recipient_name}"


def local_now(now: datetime | None = None) -> datetime:
    """Ortszeit ohne tzinfo (wie die Leistungszeiträume gespeichert sind)."""
    now = now or datetime.now(UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    return now.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def local_to_utc(value: datetime) -> datetime:
    """Ortszeit (naiv) → UTC (naiv)."""
    return (
        value.replace(tzinfo=LOCAL_TIMEZONE)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )


def utc_to_local(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=UTC)
        .astimezone(LOCAL_TIMEZONE)
        .replace(tzinfo=None)
    )


def _run_time(global_settings: GlobalSettings) -> time:
    return parse_start_time(global_settings.auto_billing_run_time)


def last_period_end(db: Session) -> datetime | None:
    return db.scalar(select(func.max(BillingRun.period_end)))


def upcoming_period(
    db: Session,
    global_settings: GlobalSettings,
    today: date,
) -> BillingPeriod:
    """Nächster Leistungszeitraum ohne Abrechnungslauf."""
    return next_period(
        interval=global_settings.auto_billing_interval,
        cutoff_day=global_settings.auto_billing_cutoff_day,
        active_since=global_settings.auto_billing_active_since or today,
        last_period_end=last_period_end(db),
    )


def data_ready(
    global_settings: GlobalSettings,
    period_end: datetime,
) -> bool:
    """
    Liegen die Ladevorgänge bis zum Ende des Zeitraums vor? Nur prüfbar,
    wenn der automatische Hager-Abruf läuft; bei manuellem Import (XLSX,
    JSON) ist der Administrator selbst verantwortlich, die Puffertage
    geben ihm Zeit dafür.
    """
    if not global_settings.hager_auto_import_enabled:
        return True

    last_fetch = global_settings.hager_last_successful_fetch_at

    return last_fetch is not None and last_fetch >= local_to_utc(period_end)


def billable_user_ids(
    db: Session,
    period_start: datetime,
    period_end: datetime,
) -> list[int]:
    """Kunden mit mindestens einer Kartenzuordnung im Zeitraum."""
    return list(
        db.scalars(
            select(RFIDCardAssignment.user_id)
            .where(
                RFIDCardAssignment.valid_from < period_end,
                or_(
                    RFIDCardAssignment.valid_to.is_(None),
                    RFIDCardAssignment.valid_to > period_start,
                ),
            )
            .distinct()
        ).all()
    )


def overlapping_draft(
    db: Session,
    user_id: int,
    period_start: datetime,
    period_end: datetime,
) -> Invoice | None:
    return db.scalar(
        select(Invoice)
        .where(
            Invoice.user_id == user_id,
            Invoice.status == "draft",
            Invoice.document_type == "invoice",
            Invoice.service_period_start < period_end,
            Invoice.service_period_end > period_start,
        )
        .order_by(Invoice.id)
        .limit(1)
    )


def _notify_issuer(action: Callable[[], None], what: str) -> None:
    """Hinweise an den Rechnungssteller dürfen den Lauf nicht abbrechen."""
    try:
        action()
    except MAIL_ERRORS as exc:
        logger.warning("Automatic billing: %s not sent: %s", what, exc)
    except Exception:
        logger.exception("Automatic billing: %s not sent", what)


# --- Schritt 1: Lauf anlegen -----------------------------------------------


def create_due_run(
    db: Session,
    global_settings: GlobalSettings,
    now_local: datetime,
) -> BillingRun | None:
    period = upcoming_period(db, global_settings, now_local.date())

    due_at = run_at(
        period.cutoff,
        global_settings.auto_billing_grace_days,
        _run_time(global_settings),
    )

    if now_local < due_at:
        return None

    run = BillingRun(
        period_start=period.start,
        period_end=period.end,
        cutoff_date=period.cutoff,
        interval=global_settings.auto_billing_interval,
        status=RUN_WAITING_FOR_DATA,
    )
    db.add(run)

    try:
        db.commit()
    except IntegrityError:
        # derselbe Zeitraum wurde gerade anderweitig angelegt
        db.rollback()
        return None

    logger.info(
        "Automatic billing: run %s for %s – %s created",
        run.id,
        period.start,
        period.end,
    )

    return run


# --- Schritt 2/3: Entwürfe erstellen und zur Prüfung senden ----------------


@dataclass
class DraftRunResult:
    created: list[Invoice] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


def send_review_notification(db: Session, invoice: Invoice) -> bool:
    """Prüf-E-Mail senden und Ergebnis am Entwurf festhalten."""
    try:
        billing_email.send_review_email(db, invoice=invoice)
    except MAIL_ERRORS as exc:
        db.rollback()
        invoice.notification_attempts = (invoice.notification_attempts or 0) + 1
        invoice.notification_error = _short(exc)
        db.commit()
        logger.warning(
            "Automatic billing: review email for invoice %s failed: %s",
            invoice.id,
            exc,
        )
        return False

    invoice.review_notified_at = utc_now()
    invoice.notification_error = None
    db.commit()

    return True


def create_drafts_for_run(
    db: Session,
    run: BillingRun,
    global_settings: GlobalSettings,
    now_local: datetime,
) -> DraftRunResult:
    result = DraftRunResult()
    review_due_date = now_local.date() + timedelta(
        days=global_settings.auto_billing_review_days
    )
    period_start = run.period_start
    period_end = run.period_end
    run_id = run.id

    users = sorted(
        (
            user
            for user in (
                db.get(User, user_id)
                for user_id in billable_user_ids(db, period_start, period_end)
            )
            if user is not None
        ),
        key=lambda user: (user.last_name, user.first_name, user.id),
    )

    for user in users:
        name = f"{user.first_name} {user.last_name}".strip()
        existing = overlapping_draft(db, user.id, period_start, period_end)

        if existing is not None:
            if existing.billing_run_id == run_id:
                # bereits in diesem Lauf erstellt (Lauf wurde unterbrochen)
                result.created.append(existing)
            else:
                result.skipped.append(
                    {
                        "user_id": user.id,
                        "name": name,
                        "reason": "existing_draft",
                        "invoice_id": existing.id,
                    }
                )
            continue

        try:
            invoice = create_invoice_draft(
                db,
                user_id=user.id,
                service_period_start=period_start,
                service_period_end=period_end,
                # Grundgebühr anteilig für die Tage im Zeitraum; bei
                # Kalendermonaten identisch mit der Monatsabrechnung
                prorate_base_fee=True,
            )
        except NoBillableSessionsError:
            continue
        except InvoiceDraftError as exc:
            result.skipped.append(
                {
                    "user_id": user.id,
                    "name": name,
                    "reason": "error",
                    "message": _short(exc),
                }
            )
            continue
        except Exception as exc:
            db.rollback()
            logger.exception(
                "Automatic billing: draft for user %s failed",
                user.id,
            )
            result.skipped.append(
                {
                    "user_id": user.id,
                    "name": name,
                    "reason": "error",
                    "message": f"Unexpected error: {type(exc).__name__}",
                }
            )
            continue

        invoice.billing_run_id = run_id
        invoice.review_status = REVIEW_IN_REVIEW
        invoice.review_due_date = review_due_date
        invoice.notification_attempts = 0
        invoice.notification_error = None
        db.commit()
        result.created.append(invoice)

    return result


def process_waiting_run(
    db: Session,
    run: BillingRun,
    global_settings: GlobalSettings,
    now_local: datetime,
) -> bool:
    """Erstellt die Entwürfe, sobald die Ladedaten vorliegen."""
    if not data_ready(global_settings, run.period_end):
        if run.waiting_notified_at is None:
            last_fetch = global_settings.hager_last_successful_fetch_at
            period_start, period_end = run.period_start, run.period_end
            _notify_issuer(
                lambda: billing_email.send_waiting_for_data_email(
                    db,
                    period_start=period_start,
                    period_end=period_end,
                    last_fetch_local=(
                        utc_to_local(last_fetch)
                        if last_fetch is not None
                        else None
                    ),
                ),
                "waiting notice",
            )
            run.waiting_notified_at = utc_now()
            db.commit()

        return False

    result = create_drafts_for_run(db, run, global_settings, now_local)

    notify_failed: list[SummaryEntry] = []

    for invoice in result.created:
        if invoice.review_notified_at is not None:
            continue

        if not send_review_notification(db, invoice):
            notify_failed.append(
                SummaryEntry(
                    _customer_label(invoice),
                    invoice.notification_error,
                )
            )

    review_due_date = now_local.date() + timedelta(
        days=global_settings.auto_billing_review_days
    )

    run.status = RUN_IN_REVIEW if result.created else RUN_COMPLETED
    run.drafts_created = len(result.created)
    run.review_due_date = review_due_date if result.created else None
    # ohne Namen speichern: nach dem Löschen eines Kunden (DSGVO) bleiben
    # im Protokoll keine personenbezogenen Daten zurück
    run.details = (
        json.dumps(
            [
                {key: value for key, value in entry.items() if key != "name"}
                for entry in result.skipped
            ],
            ensure_ascii=False,
        )
        if result.skipped
        else None
    )
    run.drafts_created_at = utc_now()

    if not result.created:
        run.completed_at = utc_now()

    db.commit()

    period_start, period_end = run.period_start, run.period_end
    skipped_entries = [
        SummaryEntry(
            entry["name"],
            translate(
                normalize_language(global_settings.default_language),
                "billing.reason.existingDraft",
                id=entry["invoice_id"],
            )
            if entry["reason"] == "existing_draft"
            else entry.get("message"),
        )
        for entry in result.skipped
    ]

    _notify_issuer(
        lambda: billing_email.send_drafts_created_email(
            db,
            period_start=period_start,
            period_end=period_end,
            created=len(result.created),
            review_due_date=review_due_date,
            skipped=skipped_entries,
            notify_failed=notify_failed,
        ),
        "draft summary",
    )

    logger.info(
        "Automatic billing: run %s – %s drafts, %s skipped",
        run.id,
        len(result.created),
        len(result.skipped),
    )

    return True


def retry_review_notifications(db: Session) -> None:
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_IN_REVIEW,
            Invoice.review_notified_at.is_(None),
            Invoice.notification_attempts > 0,
            Invoice.notification_attempts < MAX_NOTIFICATION_ATTEMPTS,
        )
    ).all()

    for invoice in invoices:
        send_review_notification(db, invoice)


# --- Schritt 4: finalisieren und zustellen ---------------------------------


@dataclass
class FinalizeSummary:
    finalized: int = 0
    sent: list[SummaryEntry] = field(default_factory=list)
    postal: list[SummaryEntry] = field(default_factory=list)
    failed: list[SummaryEntry] = field(default_factory=list)


def deliver_invoice(db: Session, invoice: Invoice) -> str:
    """
    Stellt eine automatisch finalisierte Rechnung zu (wie der Button
    "Per E-Mail senden"). Rückgabe: neuer delivery_status.
    """
    user = invoice.user

    if user is None:
        invoice.delivery_status = DELIVERY_FAILED
        invoice.notification_attempts = MAX_NOTIFICATION_ATTEMPTS
        invoice.notification_error = "No user account is assigned."
        db.commit()
        return DELIVERY_FAILED

    invoice_id = invoice.id
    postal_only = user.invoice_delivery_post and not user.invoice_delivery_email

    try:
        # PDF archivieren (wird es schon, prüft das nur die Datei); auch für
        # den Postversand, damit es gedruckt werden kann
        archive_invoice_pdf(db, invoice_id=invoice_id)

        if not postal_only:
            send_invoice_email(db, invoice_id=invoice_id)
    except (InvoiceArchiveError, InvoicePdfError, *MAIL_ERRORS) as exc:
        db.rollback()
        invoice = db.get(Invoice, invoice_id)
        invoice.delivery_status = DELIVERY_FAILED
        invoice.notification_attempts = (invoice.notification_attempts or 0) + 1
        invoice.notification_error = _short(exc)
        db.commit()
        logger.warning(
            "Automatic billing: delivery of invoice %s failed: %s",
            invoice_id,
            exc,
        )
        return DELIVERY_FAILED

    status = DELIVERY_POSTAL if postal_only else DELIVERY_SENT
    invoice = db.get(Invoice, invoice_id)
    invoice.delivery_status = status
    invoice.notification_error = None
    db.commit()

    return status


def finalize_reviewed_draft(
    db: Session,
    invoice_id: int,
    issue_date: date,
    summary: FinalizeSummary,
) -> None:
    # Zeile sperren und Prüfstatus erneut lesen: eine Nachfrage des Kunden
    # kann zwischen Auswahl und Finalisierung eingegangen sein
    invoice = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )

    if (
        invoice is None
        or invoice.status != "draft"
        or invoice.review_status != REVIEW_IN_REVIEW
    ):
        db.rollback()
        return

    label = _customer_label(invoice)

    try:
        invoice = finalize_invoice(
            db,
            invoice_id=invoice_id,
            issue_date=issue_date,
        )
    except InvoiceDraftError as exc:
        db.rollback()
        invoice = db.get(Invoice, invoice_id)
        invoice.review_status = REVIEW_FAILED
        invoice.notification_error = _short(exc)
        db.commit()
        summary.failed.append(SummaryEntry(label, _short(exc)))
        logger.warning(
            "Automatic billing: finalizing invoice %s failed: %s",
            invoice_id,
            exc,
        )
        return

    summary.finalized += 1
    label = f"{invoice.invoice_number} {invoice.recipient_name}"
    invoice.delivery_status = DELIVERY_PENDING
    invoice.notification_attempts = 0
    invoice.notification_error = None
    db.commit()

    status = deliver_invoice(db, invoice)
    invoice = db.get(Invoice, invoice_id)

    if status == DELIVERY_SENT:
        summary.sent.append(SummaryEntry(label))

        if invoice.user is not None and invoice.user.invoice_delivery_post:
            summary.postal.append(SummaryEntry(label))
    elif status == DELIVERY_POSTAL:
        summary.postal.append(SummaryEntry(label))
    else:
        summary.failed.append(SummaryEntry(label, invoice.notification_error))


def finalize_due_drafts(
    db: Session,
    global_settings: GlobalSettings,
    now_local: datetime,
) -> FinalizeSummary:
    """Finalisiert Entwürfe, deren Prüffrist abgelaufen ist."""
    today = now_local.date()
    due_through = (
        today
        if now_local.time() >= _run_time(global_settings)
        else today - timedelta(days=1)
    )

    invoice_ids = db.scalars(
        select(Invoice.id)
        .where(
            Invoice.status == "draft",
            Invoice.review_status == REVIEW_IN_REVIEW,
            Invoice.review_due_date <= due_through,
            # ohne zugestellte Prüf-E-Mail keine automatische Finalisierung
            Invoice.review_notified_at.is_not(None),
        )
        .order_by(Invoice.id)
    ).all()
    db.rollback()

    summary = FinalizeSummary()

    for invoice_id in invoice_ids:
        try:
            finalize_reviewed_draft(db, invoice_id, today, summary)
        except Exception as exc:
            db.rollback()
            logger.exception(
                "Automatic billing: finalizing invoice %s failed",
                invoice_id,
            )
            summary.failed.append(
                SummaryEntry(
                    f"#{invoice_id}",
                    f"Unexpected error: {type(exc).__name__}",
                )
            )

    if invoice_ids:
        _notify_issuer(
            lambda: billing_email.send_finalized_email(
                db,
                sent=summary.sent,
                postal=summary.postal,
                failed=summary.failed,
                finalized_count=summary.finalized,
            ),
            "finalization summary",
        )

    return summary


def retry_deliveries(db: Session) -> None:
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.status == "finalized",
            Invoice.billing_run_id.is_not(None),
            Invoice.delivery_status.in_((DELIVERY_PENDING, DELIVERY_FAILED)),
            Invoice.notification_attempts < MAX_NOTIFICATION_ATTEMPTS,
        )
    ).all()

    for invoice in invoices:
        deliver_invoice(db, invoice)


def complete_runs(db: Session) -> None:
    """Ein Lauf ist abgeschlossen, wenn keiner seiner Entwürfe offen ist."""
    runs = db.scalars(
        select(BillingRun).where(BillingRun.status == RUN_IN_REVIEW)
    ).all()

    for run in runs:
        open_drafts = db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.billing_run_id == run.id,
                Invoice.status == "draft",
            )
        )

        if not open_drafts:
            run.status = RUN_COMPLETED
            run.completed_at = utc_now()

    db.commit()


# --- ein Mandant -----------------------------------------------------------


def process_tenant(db: Session, now: datetime | None = None) -> None:
    """Alle fälligen Schritte für einen Mandanten."""
    now_local = local_now(now)
    global_settings = db.get(GlobalSettings, 1)

    if (
        global_settings is None
        or not global_settings.auto_billing_enabled
    ):
        return

    # Wiederholungen zuerst: was in diesem Durchgang neu scheitert, wird
    # erst beim nächsten Durchgang erneut versucht
    retry_review_notifications(db)
    retry_deliveries(db)

    create_due_run(db, global_settings, now_local)

    waiting_runs = db.scalars(
        select(BillingRun)
        .where(BillingRun.status == RUN_WAITING_FOR_DATA)
        .order_by(BillingRun.period_start)
    ).all()

    for run in waiting_runs:
        # ältere Zeiträume zuerst; wartet einer, warten auch die späteren
        if not process_waiting_run(db, run, global_settings, now_local):
            break

    finalize_due_drafts(db, global_settings, now_local)
    complete_runs(db)


# --- Nachfrage des Kunden --------------------------------------------------


def request_review_hold(
    db: Session,
    *,
    invoice_id: int,
    user: User,
) -> tuple[Invoice, str | None]:
    """
    "Nachfrage zum Rechnungsentwurf": stellt den Entwurf zurück (keine
    automatische Finalisierung) und benachrichtigt den Rechnungssteller.
    Rückgabe: Entwurf und Kontaktadresse für den Kunden.
    """
    invoice = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )

    if (
        invoice is None
        or invoice.user_id != user.id
        or invoice.review_status is None
        or invoice.status != "draft"
    ):
        db.rollback()
        raise InquiryNotFoundError(f"Invoice draft {invoice_id} was not found.")

    contact_email = billing_email.notification_address(db)

    if invoice.review_status == REVIEW_ON_HOLD:
        # bereits zurückgestellt: keine zweite Benachrichtigung
        db.rollback()
        return invoice, contact_email

    if invoice.review_status != REVIEW_IN_REVIEW:
        db.rollback()
        raise InquiryStateError(
            "A question about this draft is no longer possible."
        )

    invoice.review_status = REVIEW_ON_HOLD
    invoice.inquiry_at = utc_now()
    db.commit()
    db.refresh(invoice)

    logger.info(
        "Automatic billing: invoice draft %s put on hold by user %s",
        invoice.id,
        user.id,
    )

    if contact_email is not None:
        _notify_issuer(
            lambda: billing_email.send_inquiry_email(
                db,
                invoice=invoice,
                user=user,
                contact_email=contact_email,
            ),
            "inquiry notice",
        )
    else:
        logger.warning(
            "Automatic billing: no notification address for inquiry on "
            "invoice %s",
            invoice.id,
        )

    return invoice, contact_email


# --- Scheduler -------------------------------------------------------------


def _get_executor() -> ThreadPoolExecutor:
    global _executor

    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="auto-billing",
            )

        return _executor


def _default_session_factory(tenant: TenantContext) -> Session:
    from app.database import tenant_session_provider

    return tenant_session_provider.create_session(tenant)


def _default_tenants() -> list[TenantContext]:
    from app.tenancy.registry import tenant_registry

    return tenant_registry.list_active()


def run_tenant(
    tenant: TenantContext,
    session_factory: SessionFactory = _default_session_factory,
    now: datetime | None = None,
) -> None:
    try:
        db = session_factory(tenant)
    except Exception:
        logger.exception(
            "Automatic billing for tenant %s: database not available",
            tenant.slug,
        )

        with _state_lock:
            _running_tenants.discard(tenant.id)

        return

    try:
        process_tenant(db, now)
    except Exception:
        db.rollback()
        logger.exception(
            "Automatic billing for tenant %s failed",
            tenant.slug,
        )
    finally:
        db.close()

        with _state_lock:
            _running_tenants.discard(tenant.id)


def check_all_tenants(
    now: datetime | None = None,
    list_tenants: Callable[[], list[TenantContext]] = _default_tenants,
    session_factory: SessionFactory = _default_session_factory,
    submit: Submit | None = None,
) -> int:
    """Startet die Prüfung für fällige Mandanten. Rückgabe: Anzahl."""
    now = now or datetime.now(UTC)

    try:
        tenants = list_tenants()
    except Exception:
        logger.exception("Automatic billing: tenants could not be read")
        return 0

    started = 0

    for tenant in tenants:
        with _state_lock:
            if tenant.id in _running_tenants:
                continue

            last_check = _last_checks.get(tenant.id)

            if last_check is not None and now - last_check < CHECK_INTERVAL:
                continue

            _last_checks[tenant.id] = now
            _running_tenants.add(tenant.id)

        try:
            (submit or _get_executor().submit)(
                run_tenant,
                tenant,
                session_factory,
                now,
            )
            started += 1
        except Exception:
            with _state_lock:
                _running_tenants.discard(tenant.id)
            logger.exception(
                "Automatic billing for tenant %s could not be started",
                tenant.slug,
            )

    return started


def shutdown() -> None:
    global _executor

    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
