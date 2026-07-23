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
    InvoiceAlreadyFinalizedError,
    InvoiceNotFoundError,
    InvalidServicePeriodError,
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
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
        address=None,
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
