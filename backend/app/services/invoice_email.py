from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.i18n import bilingual_subject, bilingual_text, translate
from app.models.invoice import Invoice
from app.models.global_settings import GlobalSettings
from app.services.invoice_archive import (
    InvoiceArchiveError,
    get_archived_invoice_pdf,
)
from app.services.mail_smime import (
    MailSmimeConfigurationError,
    sign_configured_message,
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
                        "The saved SMTP password could not be used."
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
            "Email delivery is disabled."
        )

    if smtp_host is None:
        raise InvoiceEmailConfigurationError(
            "The SMTP host is not configured."
        )

    if smtp_port is None:
        raise InvoiceEmailConfigurationError(
            "The SMTP port is not configured."
        )

    if smtp_timeout is None:
        raise InvoiceEmailConfigurationError(
            "The SMTP timeout is not configured."
        )

    if from_address is None:
        raise InvoiceEmailConfigurationError(
            "The sender address is not configured."
        )

    if from_name is None:
        raise InvoiceEmailConfigurationError(
            "The sender name is not configured."
        )

    if (
        smtp_username is not None
        and smtp_password is None
    ):
        raise InvoiceEmailConfigurationError(
            "No password is configured for the SMTP username."
        )

    if (
        smtp_password is not None
        and smtp_username is None
    ):
        raise InvoiceEmailConfigurationError(
            "No username is configured for the SMTP password."
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
        "Witty-Accounting "
        + bilingual_subject("test.smtp.subject")
    )

    message.set_content(
        bilingual_text(
            lambda language: _test_body(
                language,
                "test.smtp.body",
                sender_name,
            )
        ),
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
            "No email address is stored for the administrator."
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
            "The SMTP test message could not be sent."
        ),
    )

    return SmtpTestEmailResult(
        recipient_email=(
            normalized_recipient_email
        ),
        subject=str(message["Subject"]),
    )


def build_smime_test_message(
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
        "Witty-Accounting "
        + bilingual_subject("test.smime.subject")
    )
    message.set_content(
        bilingual_text(
            lambda language: _test_body(
                language,
                "test.smime.body",
                sender_name,
            )
        ),
        subtype="plain",
        charset="utf-8",
    )

    return message


def send_smime_test_email(
    db: Session,
    *,
    recipient_email: str,
) -> SmtpTestEmailResult:
    normalized_recipient_email = (
        recipient_email.strip()
    )

    if not normalized_recipient_email:
        raise InvoiceEmailRecipientError(
            "No email address is stored for the administrator."
        )

    smtp_configuration = load_smtp_configuration(
        db
    )
    message = build_smime_test_message(
        recipient_email=normalized_recipient_email,
        sender_email=smtp_configuration.from_address,
        sender_name=smtp_configuration.from_name,
    )

    try:
        signed_message = sign_configured_message(
            db,
            message=message,
            sender_email=(
                smtp_configuration.from_address
            ),
            require_enabled=False,
        )
    except MailSmimeConfigurationError as exc:
        raise InvoiceEmailConfigurationError(
            f"The S/MIME test message could not be signed: {exc}"
        ) from exc

    if signed_message is None:
        raise InvoiceEmailConfigurationError(
            "The S/MIME configuration is incomplete."
        )

    deliver_email_message(
        smtp_configuration,
        message=message,
        recipient_email=normalized_recipient_email,
        signed_message=signed_message,
        delivery_error_message=(
            "The S/MIME test message could not be sent."
        ),
    )

    return SmtpTestEmailResult(
        recipient_email=normalized_recipient_email,
        subject=str(message["Subject"]),
    )


def _test_body(language: str, body_key: str, sender_name: str) -> str:
    return (
        f"{translate(language, 'email.greeting')}\n\n"
        f"{translate(language, body_key)}\n\n"
        f"{translate(language, 'email.closing')}\n"
        f"{sender_name}\n"
    )


def create_subject(invoice: Invoice) -> str:
    """Betreff in der Sprache der Rechnung."""
    return translate(
        invoice.language,
        "email.subject.cancellation"
        if invoice.document_type == "cancellation"
        else "email.subject.invoice",
        number=invoice.invoice_number,
    )


def create_body(
    invoice: Invoice,
    *,
    sender_name: str,
    portal_url: str | None = None,
) -> str:
    """Text in der Sprache der Rechnung."""
    language = invoice.language
    document = (
        "cancellation"
        if invoice.document_type == "cancellation"
        else "invoice"
    )

    delivery_text = (
        translate(
            language,
            f"email.portal.{document}",
            number=invoice.invoice_number,
        )
        + f"\n{portal_url}\n"
        if portal_url is not None
        else translate(
            language,
            f"email.attachment.{document}",
            number=invoice.invoice_number,
        )
        + "\n"
    )

    return (
        f"{translate(language, 'email.greeting')}\n\n"
        f"{delivery_text}\n"
        f"{translate(language, 'email.closing')}\n"
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
    db: Session,
    *,
    message: EmailMessage,
    sender_email: str,
) -> bytes | None:
    try:
        return sign_configured_message(
            db,
            message=message,
            sender_email=sender_email,
        )
    except MailSmimeConfigurationError as exc:
        raise InvoiceEmailConfigurationError(
            f"The invoice could not be signed with S/MIME: {exc}"
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
            f"Invoice {invoice_id} was not found."
        )

    if invoice.status != "finalized":
        raise InvoiceEmailStateError(
            "Only finalized invoices can be sent by email."
        )

    if not invoice.invoice_number:
        raise InvoiceEmailStateError(
            "The invoice has no invoice number."
        )

    user = invoice.user

    if user is None:
        raise InvoiceEmailRecipientError(
            "No user is assigned to the invoice."
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
            "Postal delivery is selected for this user."
        )

    recipient_email = user.email.strip()

    if not recipient_email:
        raise InvoiceEmailRecipientError(
            "No email address is stored for the user."
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
            f"The archived invoice PDF is not available: {exc}"
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
        db,
        message=message,
        sender_email=sender_email,
    )

    deliver_email_message(
        smtp_configuration,
        message=message,
        recipient_email=recipient_email,
        signed_message=signed_message,
        delivery_error_message=(
            "The invoice could not be sent by email."
        ),
    )

    return InvoiceEmailResult(
        recipient_email=recipient_email,
        subject=str(message["Subject"]),
    )
