from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
import smtplib
import ssl

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.charging_session import (
    ChargingSession,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.rfid_card import RFIDCard
from app.models.user import User
from app.services.invoice_archive import (
    archive_invoice_pdf,
)
from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    InvoiceEmailRecipientError,
    InvoiceEmailStateError,
    send_invoice_email,
)


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ehlo_calls = 0
        self.starttls_called = False
        self.starttls_context: (
            ssl.SSLContext | None
        ) = None
        self.message: EmailMessage | None = None

        self.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> bool:
        return False

    def ehlo(self) -> tuple[int, bytes]:
        self.ehlo_calls += 1
        return 250, b"OK"

    def starttls(
        self,
        *,
        context: ssl.SSLContext,
    ) -> tuple[int, bytes]:
        self.starttls_called = True
        self.starttls_context = context
        return 220, b"Ready to start TLS"

    def send_message(
        self,
        message: EmailMessage,
    ) -> dict[str, tuple[int, bytes]]:
        self.message = message
        return {}


class FailingSMTP(FakeSMTP):
    def send_message(
        self,
        message: EmailMessage,
    ) -> dict[str, tuple[int, bytes]]:
        raise smtplib.SMTPException(
            "Testfehler"
        )


@pytest.fixture
def database_session() -> Generator[
    Session,
    None,
    None,
]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def configure_mail_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    FakeSMTP.instances.clear()

    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        tmp_path,
    )
    monkeypatch.setattr(
        settings,
        "smtp_host",
        "smtp.example.test",
    )
    monkeypatch.setattr(
        settings,
        "smtp_port",
        2525,
    )
    monkeypatch.setattr(
        settings,
        "smtp_timeout_seconds",
        7.5,
    )
    monkeypatch.setattr(
        settings,
        "smtp_starttls",
        False,
    )
    monkeypatch.setattr(
        settings,
        "mail_from_address",
        "rechnung@example.test",
    )
    monkeypatch.setattr(
        settings,
        "mail_from_name",
        "Klaus Gottschalk",
    )


def create_finalized_invoice(
    db: Session,
) -> Invoice:
    user = User(
        email="recipient@example.test",
        password_hash="not-used",
        salutation=None,
        first_name="Mail",
        last_name="Empfänger",
        address=(
            "Musterweg 5\n"
            "54321 Musterstadt"
        ),
        phone=None,
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=False,
    )

    card = RFIDCard(
        rfid_number="MAIL-CARD",
        description="Mailtest",
        active=True,
    )

    charging_session = ChargingSession(
        hager_session_id=None,
        station_id="WB2",
        start_time=datetime(
            2026,
            6,
            17,
            10,
            0,
        ),
        end_time=datetime(
            2026,
            6,
            17,
            11,
            0,
        ),
        rfid_card=card,
        energy_total_kwh=10.0,
        energy_pv_kwh=4.0,
        cost_grid_net=Decimal("1.8000"),
        cost_pv_net=Decimal("0.4000"),
        vat_rate=Decimal("19.00"),
        invoiced=True,
        invoice_id=None,
        import_hash="m" * 64,
        source="xlsx",
    )

    invoice = Invoice(
        invoice_number="RE-2026-000001",
        document_type="invoice",
        user=user,
        issuer_name="Witty Accounting GmbH",
        issuer_address=(
            "Teststraße 1\n"
            "12345 Teststadt"
        ),
        issuer_tax_number="123/456/78901",
        issuer_vat_id=None,
        recipient_name="Mail Empfänger",
        recipient_address=(
            "Musterweg 5\n"
            "54321 Musterstadt"
        ),
        status="finalized",
        issue_date=date(2026, 7, 5),
        due_date=date(2026, 7, 19),
        service_period_start=datetime(
            2026,
            6,
            1,
        ),
        service_period_end=datetime(
            2026,
            7,
            1,
        ),
        currency="EUR",
        total_net=Decimal("2.20"),
        vat_amount=Decimal("0.42"),
        total_gross=Decimal("2.62"),
        finalized_at=datetime(
            2026,
            7,
            5,
            10,
            0,
        ),
        pdf_storage_path=None,
        pdf_sha256=None,
        pdf_size_bytes=None,
        pdf_created_at=None,
    )

    invoice.items = [
        InvoiceItem(
            item_type="charging_session",
            charging_session=charging_session,
            position_number=1,
            description="Ladevorgang",
            session_start=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            session_end=datetime(
                2026,
                6,
                17,
                11,
                0,
            ),
            station_id="WB2",
            energy_total_kwh=Decimal(
                "10.0000"
            ),
            energy_grid_kwh=Decimal(
                "6.0000"
            ),
            energy_pv_kwh=Decimal(
                "4.0000"
            ),
            grid_price_net=Decimal(
                "0.3000"
            ),
            pv_price_net=Decimal(
                "0.1000"
            ),
            cost_grid_net=Decimal(
                "1.8000"
            ),
            cost_pv_net=Decimal(
                "0.4000"
            ),
            net_amount=Decimal("2.2000"),
            vat_rate=Decimal("19.00"),
            vat_amount=Decimal("0.42"),
            gross_amount=Decimal("2.62"),
        )
    ]

    db.add(invoice)
    db.flush()

    charging_session.invoice_id = invoice.id

    db.commit()
    db.refresh(invoice)

    return invoice


def archive_invoice(
    db: Session,
    invoice: Invoice,
    tmp_path: Path,
) -> None:
    archive_invoice_pdf(
        db,
        invoice_id=invoice.id,
        archive_root=tmp_path,
    )


def test_sends_archived_invoice_pdf(
    database_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )
    archive_invoice(
        database_session,
        invoice,
        tmp_path,
    )

    monkeypatch.setattr(
        "app.services.invoice_email.smtplib.SMTP",
        FakeSMTP,
    )

    result = send_invoice_email(
        database_session,
        invoice_id=invoice.id,
    )

    assert result.recipient_email == (
        "recipient@example.test"
    )
    assert result.subject == (
        "Rechnung RE-2026-000001"
    )

    assert len(FakeSMTP.instances) == 1

    smtp = FakeSMTP.instances[0]

    assert smtp.host == "smtp.example.test"
    assert smtp.port == 2525
    assert smtp.timeout == 7.5
    assert smtp.ehlo_calls == 1
    assert smtp.starttls_called is False

    message = smtp.message

    assert message is not None
    assert message["From"] == (
        "Klaus Gottschalk "
        "<rechnung@example.test>"
    )
    assert message["To"] == (
        "recipient@example.test"
    )
    assert message["Subject"] == (
        "Rechnung RE-2026-000001"
    )

    plain_body = message.get_body(
        preferencelist=("plain",)
    )

    assert plain_body is not None
    assert (
        "RE-2026-000001"
        in plain_body.get_content()
    )

    attachments = list(
        message.iter_attachments()
    )

    assert len(attachments) == 1

    attachment = attachments[0]

    assert (
        attachment.get_content_type()
        == "application/pdf"
    )
    assert attachment.get_filename() == (
        "RE-2026-000001.pdf"
    )

    pdf_data = attachment.get_payload(
        decode=True
    )

    assert pdf_data is not None
    assert pdf_data.startswith(b"%PDF")


def test_rejects_draft_invoice(
    database_session: Session,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )
    invoice.status = "draft"
    database_session.commit()

    with pytest.raises(
        InvoiceEmailStateError,
        match="finalisierte",
    ):
        send_invoice_email(
            database_session,
            invoice_id=invoice.id,
        )


def test_rejects_disabled_email_delivery(
    database_session: Session,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    assert invoice.user is not None

    invoice.user.invoice_delivery_email = False
    database_session.commit()

    with pytest.raises(
        InvoiceEmailRecipientError,
        match="deaktiviert",
    ):
        send_invoice_email(
            database_session,
            invoice_id=invoice.id,
        )


def test_rejects_missing_sender_address(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    monkeypatch.setattr(
        settings,
        "mail_from_address",
        "   ",
    )

    with pytest.raises(
        InvoiceEmailConfigurationError,
        match="Absenderadresse",
    ):
        send_invoice_email(
            database_session,
            invoice_id=invoice.id,
        )


def test_reports_missing_archived_pdf(
    database_session: Session,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    with pytest.raises(
        InvoiceEmailStateError,
        match="archivierte",
    ):
        send_invoice_email(
            database_session,
            invoice_id=invoice.id,
        )


def test_wraps_smtp_delivery_error(
    database_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )
    archive_invoice(
        database_session,
        invoice,
        tmp_path,
    )

    monkeypatch.setattr(
        "app.services.invoice_email.smtplib.SMTP",
        FailingSMTP,
    )

    with pytest.raises(
        InvoiceEmailDeliveryError,
        match="nicht per E-Mail",
    ):
        send_invoice_email(
            database_session,
            invoice_id=invoice.id,
        )


def test_uses_starttls_when_enabled(
    database_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )
    archive_invoice(
        database_session,
        invoice,
        tmp_path,
    )

    monkeypatch.setattr(
        settings,
        "smtp_starttls",
        True,
    )
    monkeypatch.setattr(
        "app.services.invoice_email.smtplib.SMTP",
        FakeSMTP,
    )

    send_invoice_email(
        database_session,
        invoice_id=invoice.id,
    )

    smtp = FakeSMTP.instances[0]

    assert smtp.starttls_called is True
    assert isinstance(
        smtp.starttls_context,
        ssl.SSLContext,
    )
    assert smtp.ehlo_calls == 2
