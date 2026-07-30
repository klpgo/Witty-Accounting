from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.invoice import Invoice
from app.services.invoice_archive import (
    InvoiceArchiveError,
    get_archived_invoice_pdf,
)
from app.services.smime import (
    SmimeSigningError,
    sign_message,
)


class InvoiceEmailError(Exception):
    """Basisklasse für Fehler beim Rechnungsversand."""


class InvoiceEmailNotFoundError(
    InvoiceEmailError
):
    """Die Rechnung wurde nicht gefunden."""


class InvoiceEmailStateError(
    InvoiceEmailError
):
    """Die Rechnung darf nicht versendet werden."""


class InvoiceEmailRecipientError(
    InvoiceEmailError
):
    """Der Empfänger ist nicht verwendbar."""


class InvoiceEmailConfigurationError(
    InvoiceEmailError
):
    """Die Mailkonfiguration ist unvollständig."""


class InvoiceEmailDeliveryError(
    InvoiceEmailError
):
    """Der SMTP-Versand ist fehlgeschlagen."""


@dataclass(frozen=True)
class InvoiceEmailResult:
    recipient_email: str
    subject: str


def create_subject(invoice: Invoice) -> str:
    document_label = (
        "Stornorechnung"
        if invoice.document_type == "cancellation"
        else "Rechnung"
    )

    return (
        f"{document_label} "
        f"{invoice.invoice_number}"
    )

def create_body(invoice: Invoice) -> str:
    document_label = (
        "Ladestrom-Stornorechnung"
        if invoice.document_type == "cancellation"
        else "Ladestrom-Rechnung"
    )

    return (
        "Guten Tag,\n\n"
        f"im Anhang erhalten Sie Ihre {document_label} "
        f"{invoice.invoice_number} als PDF-Datei.\n\n"
        "Mit freundlichen Grüßen\n"
        f"{settings.mail_from_name}\n"
    )


def build_invoice_message(
    *,
    invoice: Invoice,
    recipient_email: str,
    pdf_data: bytes,
    pdf_filename: str,
) -> EmailMessage:
    message = EmailMessage()

    message["From"] = formataddr(
        (
            settings.mail_from_name,
            settings.mail_from_address,
        )
    )
    message["To"] = recipient_email
    message["Subject"] = create_subject(invoice)

    message.set_content(
        create_body(invoice),
        subtype="plain",
        charset="utf-8",
    )

    message.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )

    return message


def sign_invoice_message(
    *,
    message: EmailMessage,
    sender_email: str,
) -> bytes | None:
    if not settings.mail_smime_enabled:
        return None

    pkcs12_path = settings.mail_smime_pkcs12_path
    password_file = (
        settings.mail_smime_pkcs12_password_file
    )

    if pkcs12_path is None:
        raise InvoiceEmailConfigurationError(
            "Der Pfad zur S/MIME-PKCS#12-Datei "
            "ist nicht konfiguriert."
        )

    if password_file is None:
        raise InvoiceEmailConfigurationError(
            "Der Pfad zur S/MIME-Passwortdatei "
            "ist nicht konfiguriert."
        )

    try:
        return sign_message(
            message=message,
            sender_email=sender_email,
            pkcs12_path=pkcs12_path,
            password_file=password_file,
        )
    except SmimeSigningError as exc:
        raise InvoiceEmailConfigurationError(
            "Die Rechnung konnte nicht mit "
            f"S/MIME signiert werden: {exc}"
        ) from exc


def send_invoice_email(
    db: Session,
    *,
    invoice_id: int,
) -> InvoiceEmailResult:
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.user),
        )
        .where(Invoice.id == invoice_id)
    )

    if invoice is None:
        raise InvoiceEmailNotFoundError(
            f"Rechnung {invoice_id} "
            "wurde nicht gefunden."
        )

    if invoice.status != "finalized":
        raise InvoiceEmailStateError(
            "Nur finalisierte Rechnungen "
            "können per E-Mail versendet werden."
        )

    if not invoice.invoice_number:
        raise InvoiceEmailStateError(
            "Die Rechnung hat keine Rechnungsnummer."
        )

    user = invoice.user

    if user is None:
        raise InvoiceEmailRecipientError(
            "Der Rechnung ist kein Benutzer zugeordnet."
        )

    if not user.invoice_delivery_email:
        raise InvoiceEmailRecipientError(
            "Die E-Mail-Zustellung ist für diesen "
            "Benutzer deaktiviert."
        )

    recipient_email = user.email.strip()

    if not recipient_email:
        raise InvoiceEmailRecipientError(
            "Für den Benutzer ist keine "
            "E-Mail-Adresse hinterlegt."
        )

    sender_email = (
        settings.mail_from_address.strip()
    )

    if not sender_email:
        raise InvoiceEmailConfigurationError(
            "Die Absenderadresse ist nicht konfiguriert."
        )

    try:
        archived_pdf = get_archived_invoice_pdf(
            db,
            invoice_id=invoice.id,
        )
    except InvoiceArchiveError as exc:
        raise InvoiceEmailStateError(
            "Das archivierte Rechnungs-PDF "
            f"ist nicht verfügbar: {exc}"
        ) from exc

    pdf_data = (
        archived_pdf.absolute_path.read_bytes()
    )

    message = build_invoice_message(
        invoice=invoice,
        recipient_email=recipient_email,
        pdf_data=pdf_data,
        pdf_filename=(
            archived_pdf.absolute_path.name
        ),
    )

    signed_message = sign_invoice_message(
        message=message,
        sender_email=sender_email,
    )

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as smtp:
            smtp.ehlo()

            if settings.smtp_starttls:
                smtp.starttls(
                    context=ssl.create_default_context()
                )
                smtp.ehlo()

            if signed_message is None:
                smtp.send_message(message)
            else:
                smtp.sendmail(
                    sender_email,
                    [recipient_email],
                    signed_message,
                )

    except (
        OSError,
        smtplib.SMTPException,
    ) as exc:
        raise InvoiceEmailDeliveryError(
            "Die Rechnung konnte nicht per "
            "E-Mail versendet werden."
        ) from exc

    return InvoiceEmailResult(
        recipient_email=recipient_email,
        subject=str(message["Subject"]),
    )
