"""Rechnungen ohne Umsatzsteuer (Kleinunternehmer, § 19 UStG)."""
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import get_current_user, require_admin
from app.database import Base
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services.invoice_archive import (
    archive_invoice_pdf,
    get_archived_invoice_pdf,
)
from app.services.invoice_cancellation import create_cancellation_draft
from app.services.invoicing import create_invoice_draft, finalize_invoice

NOTE = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."


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
                postal_delivery_fee_net=Decimal("1.0000"),
                invoice_issuer_name="Witty Test",
                invoice_issuer_address="Testweg 1, 12345 Teststadt",
                invoice_tax_number="12345",
                vat_enabled=False,
            )
        )
        session.add(
            EnergyPrice(
                valid_from=datetime(2026, 1, 1),
                grid_price_net=Decimal("0.3000"),
                pv_price_net=Decimal("0.1000"),
                vat_rate=Decimal("19.00"),
            )
        )
        user = User(
            email="kunde@example.com",
            password_hash="not-used",
            first_name="Kunde",
            last_name="A",
            address="Teststraße 1, 12345 Teststadt",
            invoice_delivery_email=False,
            invoice_delivery_post=True,
            active=True,
            is_admin=False,
        )
        card = RFIDCard(rfid_number="CARD-1", active=True)
        assignment = RFIDCardAssignment(
            rfid_card=card,
            user=user,
            valid_from=datetime(2026, 1, 1),
        )
        session.add_all(
            [
                user,
                card,
                assignment,
                ChargingSession(
                    station_id="WB1",
                    start_time=datetime(2026, 10, 15, 10, 0),
                    end_time=datetime(2026, 10, 15, 11, 0),
                    rfid_card=card,
                    rfid_assignment=assignment,
                    energy_total_kwh=10.0,
                    energy_pv_kwh=4.0,
                    cost_grid_net=Decimal("1.8000"),
                    cost_pv_net=Decimal("0.4000"),
                    vat_rate=Decimal("19.00"),
                    invoiced=False,
                    import_hash=sha256(b"vat-session").hexdigest(),
                    source="xlsx",
                ),
            ]
        )
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def make_draft(db: Session) -> Invoice:
    return create_invoice_draft(
        db,
        user_id=db.query(User.id).scalar(),
        service_period_start=datetime(2026, 10, 1),
        service_period_end=datetime(2026, 11, 1),
    )


def pdf_text(db: Session, invoice: Invoice) -> str:
    finalize_invoice(db, invoice_id=invoice.id, issue_date=date(2026, 11, 2))
    archive_invoice_pdf(db, invoice_id=invoice.id)
    pdf = get_archived_invoice_pdf(db, invoice_id=invoice.id)

    return PdfReader(BytesIO(pdf.absolute_path.read_bytes())).pages[0].extract_text()


def test_draft_without_vat(db: Session) -> None:
    invoice = make_draft(db)

    assert invoice.vat_exempt is True
    assert invoice.vat_exemption_note == NOTE
    # Ladevorgang 2,20 + Grundgebühr 10,00 + Porto 1,00
    assert invoice.total_net == Decimal("13.20")
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.total_gross == Decimal("13.20")
    assert {item.vat_rate for item in invoice.items} == {Decimal("0.00")}
    assert {item.vat_amount for item in invoice.items} == {Decimal("0.00")}


def test_pdf_without_vat_shows_note(db: Session) -> None:
    text = pdf_text(db, make_draft(db))

    assert "Umsatzsteuer\n" not in text
    assert "Nettobetrag" not in text
    assert "USt." not in text
    assert "Betrag" in text
    assert "Rechnungsbetrag\n13,20 EUR" in text
    assert NOTE in text


def test_empty_note_is_left_out(db: Session) -> None:
    db.get(GlobalSettings, 1).vat_exemption_note = ""
    db.commit()

    invoice = make_draft(db)
    text = pdf_text(db, invoice)

    assert invoice.vat_exemption_note is None
    assert "§ 19" not in text


def test_invoice_with_vat_is_unchanged(db: Session) -> None:
    db.get(GlobalSettings, 1).vat_enabled = True
    db.commit()

    invoice = make_draft(db)
    text = pdf_text(db, invoice)

    assert invoice.vat_exempt is False
    assert invoice.vat_amount > 0
    assert "Nettobetrag" in text
    assert "§ 19" not in text


def test_cancellation_keeps_vat_exemption(db: Session) -> None:
    invoice = make_draft(db)
    finalize_invoice(db, invoice_id=invoice.id, issue_date=date(2026, 11, 2))
    # Einstellung danach wieder an: das Storno folgt der Originalrechnung
    db.get(GlobalSettings, 1).vat_enabled = True
    db.commit()

    cancellation = create_cancellation_draft(
        db,
        original_invoice_id=invoice.id,
        reason="Korrektur",
    )

    assert cancellation.vat_exempt is True
    assert cancellation.vat_exemption_note == NOTE
    assert cancellation.vat_amount == Decimal("0.00")


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: User(
        id=0,
        email="admin@example.com",
        password_hash="x",
        first_name="Admin",
        last_name="Test",
        is_admin=True,
        active=True,
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_switching_vat_is_blocked_by_open_drafts(
    client: TestClient,
    db: Session,
) -> None:
    invoice = make_draft(db)

    response = client.patch("/api/settings", json={"vat_enabled": True})
    assert response.status_code == 409
    assert db.get(GlobalSettings, 1).vat_enabled is False

    # unveränderter Wert und der Hinweistext sind trotzdem speicherbar
    response = client.patch(
        "/api/settings",
        json={"vat_enabled": False, "vat_exemption_note": "  Eigener Text  "},
    )
    assert response.status_code == 200
    assert response.json()["vat_exemption_note"] == "Eigener Text"

    finalize_invoice(db, invoice_id=invoice.id, issue_date=date(2026, 11, 2))

    response = client.patch("/api/settings", json={"vat_enabled": True})
    assert response.status_code == 200
    assert response.json()["vat_enabled"] is True

