from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.invoice import Invoice
from app.models.global_settings import GlobalSettings
from app.services.invoice_archive import (
    InvoiceArchiveError,
    get_archived_invoice_pdf,
)
from app.services.smime import (
    SmimeSigningError,
    sign_message,
)
from app.services.smtp_secret import (
    SmtpSecretError,
    decrypt_smtp_password,
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

@dataclass(frozen=True)
class SmtpTestEmailResult:
    recipient_email: str
    subject: str

@dataclass(frozen=True)
class SmtpConfiguration:
    mail_sending_enabled: bool
    host: str
    port: int
    timeout_seconds: float
    starttls: bool
    username: str | None
    password: str | None
    from_address: str
    from_name: str


def normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


def load_smtp_configuration(
    db: Session,
) -> SmtpConfiguration:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    use_database_settings = (
        global_settings is not None
        and global_settings
        .smtp_use_database_settings
    )

    if use_database_settings:
        smtp_host = normalize_optional_text(
            global_settings.smtp_host
        )
        smtp_port = global_settings.smtp_port
        smtp_timeout = (
            global_settings.smtp_timeout_seconds
        )
        smtp_starttls = bool(
            global_settings.smtp_starttls
        )
        smtp_username = normalize_optional_text(
            global_settings.smtp_username
        )
        encrypted_password = (
            normalize_optional_text(
                global_settings
                .smtp_password_encrypted
            )
        )
        from_address = normalize_optional_text(
            global_settings.mail_from_address
        )
        from_name = normalize_optional_text(
            global_settings.mail_from_name
        )
        mail_sending_enabled = (
            global_settings.mail_sending_enabled
        )

        smtp_password: str | None = None

        if encrypted_password is not None:
            try:
                smtp_password = (
                    decrypt_smtp_password(
                        encrypted_password
                    )
                )
            except SmtpSecretError as exc:
                raise (
                    InvoiceEmailConfigurationError(
                        "Das gespeicherte "
                        "SMTP-Passwort konnte nicht "
                        "verwendet werden."
                    )
                ) from exc
    else:
        smtp_host = normalize_optional_text(
            settings.smtp_host
        )
        smtp_port = settings.smtp_port
        smtp_timeout = (
            settings.smtp_timeout_seconds
        )
        smtp_starttls = settings.smtp_starttls
        smtp_username = normalize_optional_text(
            settings.smtp_username
        )
        from_address = normalize_optional_text(
            settings.mail_from_address
        )
        from_name = normalize_optional_text(
            settings.mail_from_name
        )
        mail_sending_enabled = (
            global_settings.mail_sending_enabled
            if global_settings is not None
            else True
        )

        smtp_password = None

        if settings.smtp_password is not None:
            smtp_password = (
                normalize_optional_text(
                    settings.smtp_password
                    .get_secret_value()
                )
            )

    if not mail_sending_enabled:
        raise InvoiceEmailConfigurationError(
            "Der E-Mail-Versand ist deaktiviert."
        )

    if smtp_host is None:
        raise InvoiceEmailConfigurationError(
            "Der SMTP-Host ist nicht konfiguriert."
        )

    if smtp_port is None:
        raise InvoiceEmailConfigurationError(
            "Der SMTP-Port ist nicht konfiguriert."
        )

    if smtp_timeout is None:
        raise InvoiceEmailConfigurationError(
            "Der SMTP-Timeout ist nicht konfiguriert."
        )

    if from_address is None:
        raise InvoiceEmailConfigurationError(
            "Die Absenderadresse ist nicht konfiguriert."
        )

    if from_name is None:
        raise InvoiceEmailConfigurationError(
            "Der Absendername ist nicht konfiguriert."
        )

    if (
        smtp_username is not None
        and smtp_password is None
    ):
        raise InvoiceEmailConfigurationError(
            "Für den SMTP-Benutzernamen ist "
            "kein Passwort konfiguriert."
        )

    if (
        smtp_password is not None
        and smtp_username is None
    ):
        raise InvoiceEmailConfigurationError(
            "Für das SMTP-Passwort ist kein "
            "Benutzername konfiguriert."
        )

    return SmtpConfiguration(
        mail_sending_enabled=mail_sending_enabled,
        host=smtp_host,
        port=smtp_port,
        timeout_seconds=float(smtp_timeout),
        starttls=smtp_starttls,
        username=smtp_username,
        password=smtp_password,
        from_address=from_address,
        from_name=from_name,
    )


def deliver_email_message(
    smtp_configuration: SmtpConfiguration,
    *,
    message: EmailMessage,
    recipient_email: str,
    signed_message: bytes | None = None,
    delivery_error_message: str,
) -> None:
    try:
        with smtplib.SMTP(
            smtp_configuration.host,
            smtp_configuration.port,
            timeout=(
                smtp_configuration.timeout_seconds
            ),
        ) as smtp:
            smtp.ehlo()

            if smtp_configuration.starttls:
                smtp.starttls(
                    context=ssl.create_default_context()
                )
                smtp.ehlo()

            if (
                smtp_configuration.username
                is not None
                and smtp_configuration.password
                is not None
            ):
                smtp.login(
                    smtp_configuration.username,
                    smtp_configuration.password,
                )

            if signed_message is None:
                smtp.send_message(message)
            else:
                smtp.sendmail(
                    smtp_configuration.from_address,
                    [recipient_email],
                    signed_message,
                )
    except (
        OSError,
        smtplib.SMTPException,
    ) as exc:
        raise InvoiceEmailDeliveryError(
            delivery_error_message
        ) from exc


def build_smtp_test_message(
    *,
    recipient_email: str,
    sender_email: str,
    sender_name: str,
) -> EmailMessage:
    message = EmailMessage()

    message["From"] = formataddr(
        (
            sender_name,
            sender_email,
        )
    )
    message["To"] = recipient_email
    message["Subject"] = (
        "Witty-Accounting Mailserver-Test"
    )

    message.set_content(
        "Guten Tag,\n\n"
        "diese Testnachricht bestätigt, dass die "
        "Mailserver-Einstellungen funktionieren.\n\n"
        "Mit freundlichen Grüßen\n"
        f"{sender_name}\n",
        subtype="plain",
        charset="utf-8",
    )

    return message


def send_smtp_test_email(
    db: Session,
    *,
    recipient_email: str,
) -> SmtpTestEmailResult:
    normalized_recipient_email = (
        recipient_email.strip()
    )

    if not normalized_recipient_email:
        raise InvoiceEmailRecipientError(
            "Für den Administrator ist keine "
            "E-Mail-Adresse hinterlegt."
        )

    smtp_configuration = load_smtp_configuration(
        db
    )

    message = build_smtp_test_message(
        recipient_email=(
            normalized_recipient_email
        ),
        sender_email=(
            smtp_configuration.from_address
        ),
        sender_name=(
            smtp_configuration.from_name
        ),
    )

    deliver_email_message(
        smtp_configuration,
        message=message,
        recipient_email=(
            normalized_recipient_email
        ),
        delivery_error_message=(
            "Die SMTP-Testnachricht konnte nicht "
            "versendet werden."
        ),
    )

    return SmtpTestEmailResult(
        recipient_email=(
            normalized_recipient_email
        ),
        subject=str(message["Subject"]),
    )


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

def create_body(
    invoice: Invoice,
    *,
    sender_name: str,
    portal_url: str | None = None,
) -> str:
    document_label = (
        "Ladestrom-Stornorechnung"
        if invoice.document_type == "cancellation"
        else "Ladestrom-Rechnung"
    )

    delivery_text = (
        f"Ihre {document_label} "
        f"{invoice.invoice_number} steht im Portal zum "
        "Download bereit:\n"
        f"{portal_url}\n"
        if portal_url is not None
        else (
            f"im Anhang erhalten Sie Ihre {document_label} "
            f"{invoice.invoice_number} als PDF-Datei.\n"
        )
    )

    return (
        "Guten Tag,\n\n"
        f"{delivery_text}\n"
        "Mit freundlichen Grüßen\n"
        f"{sender_name}\n"
    )


def build_invoice_message(
    *,
    invoice: Invoice,
    recipient_email: str,
    pdf_data: bytes | None,
    pdf_filename: str | None,
    sender_email: str,
    sender_name: str,
    portal_url: str | None = None,
) -> EmailMessage:
    message = EmailMessage()

    message["From"] = formataddr(
        (
            sender_name,
            sender_email,
        )
    )
    message["To"] = recipient_email
    message["Subject"] = create_subject(invoice)

    message.set_content(
        create_body(
            invoice,
            sender_name=sender_name,
            portal_url=portal_url,
        ),
        subtype="plain",
        charset="utf-8",
    )

    if pdf_data is not None and pdf_filename is not None:
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

    is_portal_delivery = (
        not user.invoice_delivery_email
        and not user.invoice_delivery_post
    )

    if (
        not user.invoice_delivery_email
        and not is_portal_delivery
    ):
        raise InvoiceEmailRecipientError(
            "Für diesen Benutzer ist die "
            "Briefzustellung ausgewählt."
        )

    recipient_email = user.email.strip()

    if not recipient_email:
        raise InvoiceEmailRecipientError(
            "Für den Benutzer ist keine "
            "E-Mail-Adresse hinterlegt."
        )

    smtp_configuration = load_smtp_configuration(
        db
    )

    sender_email = (
        smtp_configuration.from_address
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

    pdf_data = None
    pdf_filename = None
    portal_url = None

    if is_portal_delivery:
        global_settings = db.get(
            GlobalSettings,
            1,
        )
        frontend_base_url = (
            global_settings.frontend_base_url
            if global_settings is not None
            else settings.frontend_base_url
        ).strip().rstrip("/")
        portal_url = (
            f"{frontend_base_url}/invoices/{invoice.id}"
        )
    else:
        pdf_data = (
            archived_pdf.absolute_path.read_bytes()
        )
        pdf_filename = archived_pdf.absolute_path.name

    message = build_invoice_message(
        invoice=invoice,
        sender_email=sender_email,
        sender_name=(
            smtp_configuration.from_name
        ),
        recipient_email=recipient_email,
        pdf_data=pdf_data,
        pdf_filename=pdf_filename,
        portal_url=portal_url,
    )

    signed_message = sign_invoice_message(
        message=message,
        sender_email=sender_email,
    )

    deliver_email_message(
        smtp_configuration,
        message=message,
        recipient_email=recipient_email,
        signed_message=signed_message,
        delivery_error_message=(
            "Die Rechnung konnte nicht per "
            "E-Mail versendet werden."
        ),
    )

    return InvoiceEmailResult(
        recipient_email=recipient_email,
        subject=str(message["Subject"]),
    )
