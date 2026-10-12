"""E-Mail-Adresse des Rechnungsstellers auf der Rechnung (optional)."""
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.global_settings import GlobalSettings
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services.invoice_archive import (
    archive_invoice_pdf,
    get_archived_invoice_pdf,
)
from app.services.invoicing import create_invoice_draft, finalize_invoice


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            GlobalSettings(
                id=1,
                monthly_base_fee_net=Decimal("10.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
                invoice_issuer_name="Witty Test",
                invoice_issuer_address="Testweg 1, 12345 Teststadt",
                invoice_tax_number="12345",
                invoice_issuer_phone="0123 456789",
                invoice_issuer_email="rechnung@example.com",
                smtp_use_database_settings=True,
                mail_from_address="absender@example.com",
            )
        )
        user = User(
            email="kunde@example.com",
            password_hash="not-used",
            first_name="Kunde",
            last_name="A",
            address="Teststraße 1, 12345 Teststadt",
            invoice_delivery_email=True,
            invoice_delivery_post=False,
            active=True,
            is_admin=False,
        )
        card = RFIDCard(rfid_number="CARD-1", active=True)
        session.add_all(
            [
                user,
                card,
                RFIDCardAssignment(
                    rfid_card=card,
                    user=user,
                    valid_from=datetime(2026, 1, 1),
                ),
            ]
        )
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def invoice_text(db: Session) -> tuple[object, str]:
    user_id = db.query(User.id).scalar()
    invoice = create_invoice_draft(
        db,
        user_id=user_id,
        service_period_start=datetime(2026, 10, 1),
        service_period_end=datetime(2026, 11, 1),
    )
    finalize_invoice(db, invoice_id=invoice.id, issue_date=date(2026, 11, 2))
    archive_invoice_pdf(db, invoice_id=invoice.id)
    pdf = get_archived_invoice_pdf(db, invoice_id=invoice.id)
    reader = PdfReader(BytesIO(pdf.absolute_path.read_bytes()))

    return invoice, reader.pages[0].extract_text()


def test_email_appears_below_phone_when_enabled(db: Session) -> None:
    db.get(GlobalSettings, 1).invoice_issuer_email_on_invoice = True
    db.commit()

    invoice, text = invoice_text(db)

    assert invoice.issuer_email == "rechnung@example.com"
    assert "Tel.: 0123 456789\nE-Mail: rechnung@example.com" in text
    # die Absenderadresse der E-Mails erscheint nicht mehr
    assert "absender@example.com" not in text


def test_email_is_hidden_by_default(db: Session) -> None:
    invoice, text = invoice_text(db)

    assert invoice.issuer_email is None
    assert "rechnung@example.com" not in text
    assert "absender@example.com" not in text
