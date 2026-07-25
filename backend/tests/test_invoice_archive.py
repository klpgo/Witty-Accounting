from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.charging_session import (
    ChargingSession,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.rfid_card import RFIDCard
from app.models.user import User
from app.services.invoice_archive import (
    InvoicePdfIntegrityError,
    archive_invoice_pdf,
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


def create_finalized_invoice(
    db: Session,
) -> Invoice:
    user = User(
        email="archive@example.com",
        password_hash="not-used",
        salutation=None,
        first_name="Archive",
        last_name="User",
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
        user=user,
        rfid_number="ARCHIVE-CARD",
        description="Archivtest",
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
        import_hash="a" * 64,
        source="xlsx",
    )

    invoice = Invoice(
        invoice_number="RE-2026-000001",
        user=user,
        issuer_name="Witty Accounting GmbH",
        issuer_address=(
            "Teststraße 1\n"
            "12345 Teststadt"
        ),
        issuer_tax_number="123/456/78901",
        issuer_vat_id=None,
        recipient_name="Archive User",
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


def test_archives_invoice_pdf(
    database_session: Session,
    tmp_path: Path,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    result = archive_invoice_pdf(
        database_session,
        invoice_id=invoice.id,
        archive_root=tmp_path,
    )

    assert result.relative_path == (
        "2026/RE-2026-000001.pdf"
    )
    assert result.absolute_path.is_file()

    pdf_bytes = result.absolute_path.read_bytes()

    assert pdf_bytes.startswith(b"%PDF-")
    assert result.size_bytes == len(pdf_bytes)
    assert result.sha256 == sha256(
        pdf_bytes
    ).hexdigest()

    database_session.refresh(invoice)

    assert invoice.pdf_storage_path == (
        result.relative_path
    )
    assert invoice.pdf_sha256 == result.sha256
    assert invoice.pdf_size_bytes == (
        result.size_bytes
    )
    assert invoice.pdf_created_at is not None


def test_archiving_is_idempotent(
    database_session: Session,
    tmp_path: Path,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    first_result = archive_invoice_pdf(
        database_session,
        invoice_id=invoice.id,
        archive_root=tmp_path,
    )

    first_modified_time = (
        first_result.absolute_path.stat().st_mtime_ns
    )

    second_result = archive_invoice_pdf(
        database_session,
        invoice_id=invoice.id,
        archive_root=tmp_path,
    )

    assert second_result == first_result
    assert (
        second_result.absolute_path
        .stat()
        .st_mtime_ns
        == first_modified_time
    )


def test_detects_modified_archived_pdf(
    database_session: Session,
    tmp_path: Path,
) -> None:
    invoice = create_finalized_invoice(
        database_session
    )

    result = archive_invoice_pdf(
        database_session,
        invoice_id=invoice.id,
        archive_root=tmp_path,
    )

    result.absolute_path.write_bytes(
        b"manipulated"
    )

    with pytest.raises(
        InvoicePdfIntegrityError
    ):
        archive_invoice_pdf(
            database_session,
            invoice_id=invoice.id,
            archive_root=tmp_path,
        )
