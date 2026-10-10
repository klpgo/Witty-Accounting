"""
E-Mails der automatischen Abrechnung.

- Prüf-E-Mail an den Kunden (Sprache der Rechnung): Link zum Entwurf im
  Portal und Termin der automatischen Finalisierung.
- Hinweise an den Rechnungssteller (Standardsprache des Mandanten): fehlende
  Ladedaten, erstellte Entwürfe, finalisierte Rechnungen, Nachfragen.

Versand, S/MIME-Signatur und Konfiguration wie beim Rechnungsversand
(app.services.invoice_email).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy.orm import Session

from app.config import settings
from app.i18n import normalize_language, translate
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.models.user import User
from app.services.invoice_email import (
    InvoiceEmailRecipientError,
    deliver_email_message,
    load_smtp_configuration,
    normalize_optional_text,
    sign_invoice_message,
)
from app.utils import locale_format


@dataclass(frozen=True)
class SummaryEntry:
    """Eine Zeile in einer Übersicht an den Rechnungssteller."""

    label: str
    message: str | None = None


def notification_address(db: Session) -> str | None:
    """Adresse des Rechnungsstellers für Hinweise und Nachfragen."""
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is not None:
        configured = normalize_optional_text(
            global_settings.auto_billing_notification_email
        )

        if configured is not None:
            return configured

        if global_settings.smtp_use_database_settings:
            return normalize_optional_text(
                global_settings.mail_from_address
            )

    return normalize_optional_text(settings.mail_from_address)


def portal_invoice_url(db: Session, invoice_id: int) -> str:
    global_settings = db.get(GlobalSettings, 1)
    base_url = (
        global_settings.frontend_base_url
        if global_settings is not None
        else settings.frontend_base_url
    )

    return f"{base_url.strip().rstrip('/')}/invoices/{invoice_id}"


def _tenant_language(db: Session) -> str:
    global_settings = db.get(GlobalSettings, 1)

    return normalize_language(
        getattr(global_settings, "default_language", None)
    )


def _tenant_locale(db: Session) -> str:
    global_settings = db.get(GlobalSettings, 1)

    return (
        getattr(global_settings, "locale", None)
        or locale_format.DEFAULT_LOCALE
    )


def format_period(
    start: datetime,
    end: datetime,
    locale: str | None,
) -> str:
    """Leistungszeitraum mit letztem Tag (Ende ist exklusiv)."""
    last_day = end.date()

    if end.time() == time(0, 0) and end > start:
        last_day = (end - timedelta(days=1)).date()

    return (
        f"{locale_format.format_date(start.date(), locale)} – "
        f"{locale_format.format_date(last_day, locale)}"
    )


def invoice_period(invoice: Invoice, locale: str | None = None) -> str:
    return format_period(
        invoice.service_period_start,
        invoice.service_period_end,
        locale or invoice.locale,
    )


def invoice_amount(invoice: Invoice, locale: str | None = None) -> str:
    return locale_format.format_money(
        invoice.total_gross,
        invoice.currency,
        locale or invoice.locale,
    )


def send_plain_email(
    db: Session,
    *,
    recipient_email: str,
    subject: str,
    body: str,
    delivery_error_message: str,
) -> None:
    recipient_email = recipient_email.strip()

    if not recipient_email:
        raise InvoiceEmailRecipientError(
            "No recipient email address is available."
        )

    smtp_configuration = load_smtp_configuration(db)

    message = EmailMessage()
    message["From"] = formataddr(
        (
            smtp_configuration.from_name,
            smtp_configuration.from_address,
        )
    )
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(
        body,
        subtype="plain",
        charset="utf-8",
    )

    signed_message = sign_invoice_message(
        db,
        message=message,
        sender_email=smtp_configuration.from_address,
    )

    deliver_email_message(
        smtp_configuration,
        message=message,
        recipient_email=recipient_email,
        signed_message=signed_message,
        delivery_error_message=delivery_error_message,
    )


def _letter(language: str, text: str, sender_name: str) -> str:
    return (
        f"{translate(language, 'email.greeting')}\n\n"
        f"{text}\n\n"
        f"{translate(language, 'email.closing')}\n"
        f"{sender_name}\n"
    )


def _sender_name(db: Session) -> str:
    try:
        return load_smtp_configuration(db).from_name
    except Exception:
        return "Witty-Accounting"


# --- an den Kunden ---------------------------------------------------------


def build_review_email(
    db: Session,
    *,
    invoice: Invoice,
    sender_name: str,
) -> tuple[str, str]:
    language = invoice.language
    period = invoice_period(invoice)
    review_due = (
        locale_format.format_date(invoice.review_due_date, invoice.locale)
        if invoice.review_due_date is not None
        else ""
    )

    subject = translate(language, "email.review.subject", period=period)
    text = (
        translate(
            language,
            "email.review.intro",
            period=period,
            amount=invoice_amount(invoice),
        )
        + "\n"
        + portal_invoice_url(db, invoice.id)
        + "\n\n"
        + translate(language, "email.review.deadline", date=review_due)
    )

    return subject, _letter(language, text, sender_name)


def send_review_email(db: Session, *, invoice: Invoice) -> str:
    """Sendet die Prüf-E-Mail; Rückgabe: Empfängeradresse."""
    user: User | None = invoice.user

    if user is None or not (user.email or "").strip():
        raise InvoiceEmailRecipientError(
            "No email address is stored for the customer."
        )

    subject, body = build_review_email(
        db,
        invoice=invoice,
        sender_name=_sender_name(db),
    )

    send_plain_email(
        db,
        recipient_email=user.email,
        subject=subject,
        body=body,
        delivery_error_message="The review email could not be sent.",
    )

    return user.email.strip()


# --- an den Rechnungssteller -----------------------------------------------


def _send_to_issuer(
    db: Session,
    *,
    subject: str,
    text: str,
) -> None:
    recipient = notification_address(db)

    if recipient is None:
        raise InvoiceEmailRecipientError(
            "No notification address is configured for automatic billing."
        )

    send_plain_email(
        db,
        recipient_email=recipient,
        subject=subject,
        body=_letter(_tenant_language(db), text, _sender_name(db)),
        delivery_error_message=(
            "The notification for automatic billing could not be sent."
        ),
    )


def _section(
    language: str,
    key: str,
    entries: list[SummaryEntry],
) -> str:
    if not entries:
        return ""

    lines = [translate(language, key)]

    for entry in entries:
        line = f"- {entry.label}"

        if entry.message:
            line += f": {entry.message}"

        lines.append(line)

    return "\n\n" + "\n".join(lines)


def send_waiting_for_data_email(
    db: Session,
    *,
    period_start: datetime,
    period_end: datetime,
    last_fetch_local: datetime | None,
) -> None:
    language = _tenant_language(db)
    locale = _tenant_locale(db)
    period = format_period(period_start, period_end, locale)
    last_fetch = (
        f"{locale_format.format_date(last_fetch_local.date(), locale)} "
        f"{last_fetch_local:%H:%M}"
        if last_fetch_local is not None
        else translate(language, "billing.never")
    )

    _send_to_issuer(
        db,
        subject=translate(
            language,
            "billing.waiting.subject",
            period=period,
        ),
        text=translate(
            language,
            "billing.waiting.body",
            period=period,
            last_fetch=last_fetch,
        ),
    )


def send_drafts_created_email(
    db: Session,
    *,
    period_start: datetime,
    period_end: datetime,
    created: int,
    review_due_date: date,
    skipped: list[SummaryEntry],
    notify_failed: list[SummaryEntry],
) -> None:
    language = _tenant_language(db)
    locale = _tenant_locale(db)
    period = format_period(period_start, period_end, locale)

    text = (
        translate(
            language,
            "billing.drafts.body",
            period=period,
            count=created,
            date=locale_format.format_date(review_due_date, locale),
        )
        if created
        else translate(language, "billing.drafts.none", period=period)
    )
    text += _section(language, "billing.section.skipped", skipped)
    text += _section(language, "billing.section.notifyFailed", notify_failed)

    _send_to_issuer(
        db,
        subject=translate(language, "billing.drafts.subject", period=period),
        text=text,
    )


def send_finalized_email(
    db: Session,
    *,
    sent: list[SummaryEntry],
    postal: list[SummaryEntry],
    failed: list[SummaryEntry],
    finalized_count: int,
) -> None:
    language = _tenant_language(db)

    text = translate(language, "billing.finalized.body")
    text += _section(language, "billing.section.sent", sent)
    text += _section(language, "billing.section.postal", postal)
    text += _section(language, "billing.section.failed", failed)

    _send_to_issuer(
        db,
        subject=translate(
            language,
            "billing.finalized.subject",
            count=finalized_count,
        ),
        text=text,
    )


def send_inquiry_email(
    db: Session,
    *,
    invoice: Invoice,
    user: User,
    contact_email: str,
) -> None:
    language = _tenant_language(db)
    locale = _tenant_locale(db)
    name = " ".join(
        part for part in (user.first_name, user.last_name) if part
    ) or invoice.recipient_name

    text = (
        translate(
            language,
            "billing.inquiry.body",
            name=name,
            email=user.email,
            id=invoice.id,
            period=invoice_period(invoice, locale),
            amount=invoice_amount(invoice, locale),
            contact=contact_email,
        )
        + "\n"
        + portal_invoice_url(db, invoice.id)
    )

    _send_to_issuer(
        db,
        subject=translate(language, "billing.inquiry.subject", name=name),
        text=text,
    )
