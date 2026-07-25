from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal

from app.models.invoice import Invoice, InvoiceItem

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.invoice import InvoiceItem
from app.models.rfid_card import RFIDCard
from app.models.user import User
from app.services.invoicing import (
    InvalidDueDateError,
    InvoiceAlreadyFinalizedError,
    InvoiceNotFoundError,
    InvalidServicePeriodError,
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
)

from app.services.invoice_cancellation import (
    InvoiceAlreadyCancelledError,
    InvoiceCancellationError,
    InvoiceCancellationNotFoundError,
    InvoiceCancellationStateError,
    create_cancellation_draft,
    finalize_cancellation,
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


def create_test_data(
    db: Session,
) -> User:
    user = User(
        email="invoice@example.com",
        password_hash="not-used",
        salutation=None,
        first_name="Invoice",
        last_name="User",
        address="Teststraße 1, 12345 Teststadt",
        phone=None,
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=False,
    )

    rfid_card = RFIDCard(
        user=user,
        rfid_number="INVOICE-CARD",
        description="Testkarte",
        active=True,
    )

    db.add(
        EnergyPrice(
            valid_from=datetime(2026, 1, 1),
            grid_price_net=Decimal("0.3000"),
            pv_price_net=Decimal("0.1000"),
            vat_rate=Decimal("19.00"),
        )
    )

    db.add(user)
    db.flush()

    db.add(
        ChargingSession(
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
            rfid_card=rfid_card,
            energy_total_kwh=10.0,
            energy_pv_kwh=4.0,
            cost_grid_net=Decimal("1.8000"),
            cost_pv_net=Decimal("0.4000"),
            vat_rate=Decimal("19.00"),
            invoiced=False,
            invoice_id=None,
            import_hash="j" * 64,
            source="xlsx",
        )
    )

    db.commit()
    db.refresh(user)

    return user


def test_creates_invoice_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    assert invoice.status == "draft"
    assert invoice.invoice_number is None
    assert invoice.issue_date is None
    assert invoice.total_net == Decimal("2.20")
    assert invoice.vat_amount == Decimal("0.42")
    assert invoice.total_gross == Decimal("2.62")

    assert len(invoice.items) == 1

    item = invoice.items[0]

    assert item.position_number == 1
    assert item.energy_total_kwh == Decimal(
        "10.0000"
    )
    assert item.energy_grid_kwh == Decimal(
        "6.0000"
    )
    assert item.energy_pv_kwh == Decimal(
        "4.0000"
    )
    assert item.grid_price_net == Decimal(
        "0.3000"
    )
    assert item.pv_price_net == Decimal(
        "0.1000"
    )
    assert item.net_amount == Decimal("2.2000")
    assert item.vat_amount == Decimal("0.42")
    assert item.gross_amount == Decimal("2.62")


def test_session_cannot_enter_second_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    with pytest.raises(
        NoBillableSessionsError
    ):
        create_invoice_draft(
            database_session,
            user_id=user.id,
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
        )

    assert (
        database_session.query(
            InvoiceItem
        ).count()
        == 1
    )


def test_rejects_invalid_service_period(
    database_session: Session,
) -> None:
    with pytest.raises(
        InvalidServicePeriodError
    ):
        create_invoice_draft(
            database_session,
            user_id=1,
            service_period_start=datetime(
                2026,
                7,
                1,
            ),
            service_period_end=datetime(
                2026,
                7,
                1,
            ),
        )

def test_finalizes_invoice_and_locks_session(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    finalized_invoice = finalize_invoice(
        database_session,
        invoice_id=invoice.id,
        issue_date=date(2026, 7, 5),
        due_date=date(2026, 7, 19),
    )

    assert finalized_invoice.status == "finalized"
    assert finalized_invoice.invoice_number == (
        f"RE-2026-{invoice.id:06d}"
    )
    assert finalized_invoice.issue_date == date(
        2026,
        7,
        5,
    )
    assert finalized_invoice.due_date == date(
        2026,
        7,
        19,
    )
    assert finalized_invoice.finalized_at is not None

    item = finalized_invoice.items[0]
    charging_session = item.charging_session

    assert charging_session.invoiced is True
    assert charging_session.invoice_id == invoice.id


def test_cannot_finalize_invoice_twice(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    finalize_invoice(
        database_session,
        invoice_id=invoice.id,
        issue_date=date(2026, 7, 5),
    )

    with pytest.raises(
        InvoiceAlreadyFinalizedError
    ):
        finalize_invoice(
            database_session,
            invoice_id=invoice.id,
            issue_date=date(2026, 7, 6),
        )


def test_rejects_unknown_invoice(
    database_session: Session,
) -> None:
    with pytest.raises(InvoiceNotFoundError):
        finalize_invoice(
            database_session,
            invoice_id=999999,
            issue_date=date(2026, 7, 5),
        )


def test_rejects_due_date_before_issue_date(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    with pytest.raises(InvalidDueDateError):
        finalize_invoice(
            database_session,
            invoice_id=invoice.id,
            issue_date=date(2026, 7, 5),
            due_date=date(2026, 7, 4),
        )


def test_creates_cancellation_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    original_item = original_invoice.items[0]

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    assert cancellation.document_type == (
        "cancellation"
    )
    assert cancellation.status == "draft"
    assert cancellation.invoice_number is None

    assert cancellation.original_invoice_id == (
        original_invoice.id
    )
    assert cancellation.cancellation_reason == (
        "Fehlerhafte Abrechnung"
    )
    assert cancellation.cancelled_at is None

    assert cancellation.total_net == (
        -original_invoice.total_net
    )
    assert cancellation.vat_amount == (
        -original_invoice.vat_amount
    )
    assert cancellation.total_gross == (
        -original_invoice.total_gross
    )

    assert len(cancellation.items) == 1

    cancellation_item = cancellation.items[0]

    assert (
        cancellation_item.charging_session_id
        is None
    )
    assert (
        cancellation_item.reversed_invoice_item_id
        == original_item.id
    )

    assert cancellation_item.energy_total_kwh == (
        -original_item.energy_total_kwh
    )
    assert cancellation_item.energy_grid_kwh == (
        -original_item.energy_grid_kwh
    )
    assert cancellation_item.energy_pv_kwh == (
        -original_item.energy_pv_kwh
    )

    assert cancellation_item.grid_price_net == (
        original_item.grid_price_net
    )
    assert cancellation_item.pv_price_net == (
        original_item.pv_price_net
    )
    assert cancellation_item.vat_rate == (
        original_item.vat_rate
    )

    assert cancellation_item.net_amount == (
        -original_item.net_amount
    )
    assert cancellation_item.vat_amount == (
        -original_item.vat_amount
    )
    assert cancellation_item.gross_amount == (
        -original_item.gross_amount
    )


def test_rejects_second_cancellation_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    with pytest.raises(
        InvoiceAlreadyCancelledError,
        match="existiert bereits",
    ):
        create_cancellation_draft(
            database_session,
            original_invoice_id=(
                original_invoice.id
            ),
            reason="Zweiter Stornoversuch",
        )


def test_rejects_cancellation_of_draft_invoice(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    with pytest.raises(
        InvoiceCancellationStateError,
        match="Nur eine finalisierte Rechnung",
    ):
        create_cancellation_draft(
            database_session,
            original_invoice_id=original_invoice.id,
            reason="Unzulässiger Stornoversuch",
        )


def test_rejects_empty_cancellation_reason(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    with pytest.raises(
        InvoiceCancellationError,
        match="Stornierungsgrund ist erforderlich",
    ):
        create_cancellation_draft(
            database_session,
            original_invoice_id=original_invoice.id,
            reason="   ",
        )


def test_rejects_cancellation_for_missing_invoice(
    database_session: Session,
) -> None:
    with pytest.raises(
        InvoiceCancellationNotFoundError,
        match="wurde nicht gefunden",
    ):
        create_cancellation_draft(
            database_session,
            original_invoice_id=999_999,
            reason="Nicht vorhandene Rechnung",
        )


def test_rejects_cancellation_of_cancellation_document(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    with pytest.raises(
        InvoiceCancellationStateError,
        match="Nur eine normale Rechnung",
    ):
        create_cancellation_draft(
            database_session,
            original_invoice_id=cancellation.id,
            reason="Storno des Stornos",
        )


def test_finalizes_cancellation_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    original_number = (
        original_invoice.invoice_number
    )
    original_finalized_at = (
        original_invoice.finalized_at
    )

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    cancellation = finalize_cancellation(
        database_session,
        cancellation_id=cancellation.id,
        issue_date=date(
            2026,
            7,
            6,
        ),
    )

    assert cancellation.status == "finalized"
    assert cancellation.document_type == (
        "cancellation"
    )
    assert cancellation.invoice_number == (
        "ST-2026-000001"
    )
    assert cancellation.issue_date == date(
        2026,
        7,
        6,
    )
    assert cancellation.due_date is None
    assert cancellation.finalized_at is not None
    assert cancellation.cancelled_at is not None

    assert cancellation.original_invoice_id == (
        original_invoice.id
    )
    assert cancellation.cancellation_reason == (
        "Fehlerhafte Abrechnung"
    )

    assert cancellation.pdf_storage_path is None
    assert cancellation.pdf_sha256 is None
    assert cancellation.pdf_size_bytes is None
    assert cancellation.pdf_created_at is None

    database_session.refresh(
        original_invoice
    )

    assert original_invoice.status == "finalized"
    assert original_invoice.invoice_number == (
        original_number
    )
    assert original_invoice.finalized_at == (
        original_finalized_at
    )
    assert original_invoice.cancelled_at is None


def test_rejects_second_cancellation_finalization(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    cancellation = finalize_cancellation(
        database_session,
        cancellation_id=cancellation.id,
        issue_date=date(
            2026,
            7,
            6,
        ),
    )

    with pytest.raises(
        InvoiceCancellationStateError,
        match="Nur ein Storno-Entwurf",
    ):
        finalize_cancellation(
            database_session,
            cancellation_id=cancellation.id,
            issue_date=date(
                2026,
                7,
                7,
            ),
        )


def test_rejects_cancellation_date_before_invoice_date(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
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
    )

    original_invoice = finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(
            2026,
            7,
            5,
        ),
    )

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Fehlerhafte Abrechnung",
    )

    with pytest.raises(
        InvoiceCancellationStateError,
        match=(
            "Stornodatum darf nicht vor "
            "dem Rechnungsdatum liegen"
        ),
    ):
        finalize_cancellation(
            database_session,
            cancellation_id=cancellation.id,
            issue_date=date(
                2026,
                7,
                4,
            ),
        )

    database_session.refresh(cancellation)

    assert cancellation.status == "draft"
    assert cancellation.invoice_number is None
    assert cancellation.issue_date is None
    assert cancellation.finalized_at is None
    assert cancellation.cancelled_at is None
