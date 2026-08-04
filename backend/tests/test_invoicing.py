from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal

from app.models.invoice import Invoice, InvoiceItem

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.services.invoicing import (
    InvalidDueDateError,
    InvoiceAlreadyFinalizedError,
    InvoiceNotFoundError,
    InvalidServicePeriodError,
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
    find_monthly_base_fee_assignments,
    InvoiceItemStateError,
)
from app.models.global_settings import GlobalSettings
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
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

    db.add(rfid_card)
    db.flush()

    rfid_assignment = RFIDCardAssignment(
        rfid_card_id=rfid_card.id,
        user_id=user.id,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
        valid_to=None,
    )

    db.add(rfid_assignment)
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
            rfid_assignment=rfid_assignment,
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


def test_uses_global_invoice_business_settings(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            invoice_issuer_name=(
                "Klaus Gottschalk"
            ),
            invoice_issuer_address=(
                "Musterstraße 1\n"
                "12345 Musterstadt"
            ),
            invoice_tax_number=None,
            invoice_vat_id="DE123456789",
            invoice_bank_name="Musterbank",
            invoice_iban=(
                "DE89370400440532013000"
            ),
            invoice_bic="COBADEFFXXX",
            invoice_number_prefix="RG",
        )
    )
    database_session.commit()

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

    assert invoice.issuer_name == (
        "Klaus Gottschalk"
    )
    assert invoice.issuer_address == (
        "Musterstraße 1\n12345 Musterstadt"
    )
    assert invoice.issuer_tax_number is None
    assert invoice.issuer_vat_id == (
        "DE123456789"
    )
    assert invoice.issuer_bank_name == (
        "Musterbank"
    )
    assert invoice.issuer_iban == (
        "DE89370400440532013000"
    )
    assert invoice.issuer_bic == (
        "COBADEFFXXX"
    )


def test_places_monthly_base_fee_before_charging_session(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

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

    assert [
        item.item_type
        for item in invoice.items
    ] == [
        "monthly_base_fee",
        "charging_session",
    ]

    assert [
        item.position_number
        for item in invoice.items
    ] == [
        1,
        2,
    ]

    monthly_base_fee_item = invoice.items[0]

    assert monthly_base_fee_item.description == (
        "Monatsgebühr RFID-Karte "
        "Testkarte - Juni 2026"
    )

    assert invoice.total_net == Decimal("12.20")
    assert invoice.vat_amount == Decimal("2.32")
    assert invoice.total_gross == Decimal("14.52")


def test_adds_postal_delivery_fee_as_last_item(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)
    user.invoice_delivery_email = False
    user.invoice_delivery_post = True

    database_session.add(
        GlobalSettings(
            id=1,
            postal_delivery_fee_net=Decimal("1.6000"),
            monthly_base_fee_vat_rate=Decimal("7.00"),
        )
    )
    database_session.commit()

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(2026, 6, 1),
        service_period_end=datetime(2026, 7, 1),
    )

    assert [item.item_type for item in invoice.items] == [
        "charging_session",
        "postal_delivery",
    ]

    postal_item = invoice.items[-1]
    assert postal_item.position_number == 2
    assert postal_item.description == "Briefporto"
    assert postal_item.net_amount == Decimal("1.6000")
    assert postal_item.vat_rate == Decimal("7.00")
    assert postal_item.vat_amount == Decimal("0.11")
    assert postal_item.gross_amount == Decimal("1.71")
    assert invoice.total_net == Decimal("3.80")
    assert invoice.vat_amount == Decimal("0.53")
    assert invoice.total_gross == Decimal("4.33")


def test_omits_zero_postal_delivery_fee(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)
    user.invoice_delivery_email = False
    user.invoice_delivery_post = True

    database_session.add(
        GlobalSettings(
            id=1,
            postal_delivery_fee_net=Decimal("0.0000"),
        )
    )
    database_session.commit()

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(2026, 6, 1),
        service_period_end=datetime(2026, 7, 1),
    )

    assert [item.item_type for item in invoice.items] == [
        "charging_session",
    ]
    assert invoice.total_gross == Decimal("2.62")


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


def test_rebills_session_after_finalized_cancellation(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    charging_session = (
        database_session.query(
            ChargingSession
        ).one()
    )

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

    original_item = original_invoice.items[0]
    original_item_id = original_item.id

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

    finalize_cancellation(
        database_session,
        cancellation_id=cancellation.id,
        issue_date=date(
            2026,
            7,
            6,
        ),
    )

    database_session.refresh(
        charging_session
    )

    assert charging_session.invoiced is False
    assert charging_session.invoice_id is None

    rebill_invoice = create_invoice_draft(
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

    assert len(rebill_invoice.items) == 1

    rebill_item = rebill_invoice.items[0]

    assert rebill_item.id != original_item_id
    assert (
        rebill_item.charging_session_id
        == charging_session.id
    )
    assert (
        rebill_item.rebills_invoice_item_id
        == original_item_id
    )

    stored_original_item = database_session.get(
        InvoiceItem,
        original_item_id,
    )

    assert stored_original_item is not None
    assert (
        stored_original_item.charging_session_id
        == charging_session.id
    )


def test_session_cannot_enter_second_rebill_draft(
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

    finalize_cancellation(
        database_session,
        cancellation_id=cancellation.id,
        issue_date=date(
            2026,
            7,
            6,
        ),
    )

    rebill_invoice = create_invoice_draft(
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

    assert len(rebill_invoice.items) == 1
    assert (
        rebill_invoice.items[0]
        .rebills_invoice_item_id
        == original_invoice.items[0].id
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

    billing_items = list(
        database_session.scalars(
            select(InvoiceItem).where(
                InvoiceItem.charging_session_id
                == original_invoice.items[
                    0
                ].charging_session_id
            )
        ).all()
    )

    assert len(billing_items) == 2


def test_finalizes_rebill_invoice(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    charging_session = (
        database_session.query(
            ChargingSession
        ).one()
    )

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

    original_invoice_id = original_invoice.id
    original_item_id = original_invoice.items[0].id
    original_invoice_number = (
        original_invoice.invoice_number
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

    cancellation_id = cancellation.id
    cancellation_number = (
        cancellation.invoice_number
    )

    rebill_invoice = create_invoice_draft(
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

    rebill_invoice_id = rebill_invoice.id
    rebill_item = rebill_invoice.items[0]

    assert (
        rebill_item.rebills_invoice_item_id
        == original_item_id
    )

    rebill_invoice = finalize_invoice(
        database_session,
        invoice_id=rebill_invoice.id,
        issue_date=date(
            2026,
            7,
            7,
        ),
    )

    database_session.refresh(
        charging_session
    )

    assert rebill_invoice.status == "finalized"
    assert rebill_invoice.invoice_number is not None
    assert rebill_invoice.id == rebill_invoice_id

    assert charging_session.invoiced is True
    assert (
        charging_session.invoice_id
        == rebill_invoice.id
    )

    stored_original = database_session.get(
        Invoice,
        original_invoice_id,
    )
    stored_cancellation = database_session.get(
        Invoice,
        cancellation_id,
    )
    stored_original_item = database_session.get(
        InvoiceItem,
        original_item_id,
    )

    assert stored_original is not None
    assert stored_original.status == "finalized"
    assert (
        stored_original.invoice_number
        == original_invoice_number
    )

    assert stored_cancellation is not None
    assert stored_cancellation.status == "finalized"
    assert (
        stored_cancellation.invoice_number
        == cancellation_number
    )

    assert stored_original_item is not None
    assert (
        stored_original_item.charging_session_id
        == charging_session.id
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


def test_uses_configured_invoice_number_prefix(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            invoice_number_prefix="RG",
        )
    )
    database_session.commit()

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

    assert finalized_invoice.invoice_number == (
        f"RG-2026-{invoice.id:06d}"
    )


def test_uses_global_payment_term_for_due_date(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            app_name="Witty-Accounting",
            monthly_base_fee_net=Decimal("0.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
            invoice_payment_term_days=14,
        )
    )
    database_session.flush()

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

    original_invoice.issuer_bank_name = (
        "Musterbank"
    )
    original_invoice.issuer_iban = (
        "DE89370400440532013000"
    )
    original_invoice.issuer_bic = (
        "COBADEFFXXX"
    )
    database_session.commit()

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
    assert cancellation.issuer_bank_name == (
        original_invoice.issuer_bank_name
    )
    assert cancellation.issuer_iban == (
        original_invoice.issuer_iban
    )
    assert cancellation.issuer_bic == (
        original_invoice.issuer_bic
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

    rfid_assignment = database_session.scalar(
        select(RFIDCardAssignment).where(
            RFIDCardAssignment.user_id
            == user.id
        )
    )

    assert rfid_assignment is not None

    rfid_card = rfid_assignment.rfid_card

    assert rfid_card is not None

    database_session.add_all(
        [
            ChargingSession(
                hager_session_id=None,
                station_id="WB2",
                start_time=datetime(
                    2026,
                    6,
                    18,
                    10,
                    0,
                ),
                end_time=datetime(
                    2026,
                    6,
                    18,
                    11,
                    0,
                ),
                rfid_card_id=rfid_card.id,
                rfid_assignment_id=(
                    rfid_assignment.id
                ),
                energy_total_kwh=8.0,
                energy_pv_kwh=2.0,
                cost_grid_net=Decimal("1.8000"),
                cost_pv_net=Decimal("0.2000"),
                vat_rate=Decimal("19.00"),
                invoiced=False,
                invoice_id=None,
                import_hash="k" * 64,
                source="xlsx",
            ),
            ChargingSession(
                hager_session_id=None,
                station_id="WB2",
                start_time=datetime(
                    2026,
                    6,
                    19,
                    10,
                    0,
                ),
                end_time=datetime(
                    2026,
                    6,
                    19,
                    11,
                    0,
                ),
                rfid_card_id=rfid_card.id,
                rfid_assignment_id=(
                    rfid_assignment.id
                ),
                energy_total_kwh=6.0,
                energy_pv_kwh=6.0,
                cost_grid_net=Decimal("0.0000"),
                cost_pv_net=Decimal("0.6000"),
                vat_rate=Decimal("19.00"),
                invoiced=False,
                invoice_id=None,
                import_hash="l" * 64,
                source="xlsx",
            ),
        ]
    )

    database_session.commit()

    charging_sessions = list(
        database_session.scalars(
            select(ChargingSession)
            .where(
                ChargingSession.rfid_card_id
                == rfid_card.id
            )
            .order_by(ChargingSession.id)
        ).all()
    )

    assert len(charging_sessions) == 3


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

    assert len(original_invoice.items) == 3

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

    assert len(cancellation.items) == 3

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

    for charging_session in charging_sessions:
        database_session.refresh(
            charging_session
        )

        assert charging_session.invoiced is False
        assert charging_session.invoice_id is None


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


def test_finds_assignment_for_each_month_start(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    assignments = (
        find_monthly_base_fee_assignments(
            database_session,
            user_id=user.id,
            service_period_start=datetime(
                2026,
                6,
                1,
            ),
            service_period_end=datetime(
                2026,
                8,
                1,
            ),
        )
    )

    assert [
        (
            assignment.rfid_card.rfid_number,
            fee_month,
        )
        for assignment, fee_month in assignments
    ] == [
        (
            "INVOICE-CARD",
            date(2026, 6, 1),
        ),
        (
            "INVOICE-CARD",
            date(2026, 7, 1),
        ),
    ]


def test_monthly_assignment_uses_half_open_period(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    assignment = database_session.scalar(
        select(RFIDCardAssignment).where(
            RFIDCardAssignment.user_id
            == user.id
        )
    )

    assert assignment is not None

    assignment.valid_from = datetime(
        2026,
        6,
        15,
    )
    assignment.valid_to = datetime(
        2026,
        8,
        1,
    )
    database_session.flush()

    assignments = (
        find_monthly_base_fee_assignments(
            database_session,
            user_id=user.id,
            service_period_start=datetime(
                2026,
                6,
                1,
            ),
            service_period_end=datetime(
                2026,
                9,
                1,
            ),
        )
    )

    assert [
        fee_month
        for _, fee_month in assignments
    ] == [
        date(2026, 7, 1),
    ]


def test_creates_base_fee_only_invoice_draft(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(
            2026,
            7,
            1,
        ),
        service_period_end=datetime(
            2026,
            8,
            1,
        ),
    )

    assert len(invoice.items) == 1

    item = invoice.items[0]

    assert item.item_type == "monthly_base_fee"
    assert item.charging_session_id is None
    assert item.monthly_base_fee_charge_id is not None
    assert item.description == (
        "Monatsgebühr RFID-Karte "
        "Testkarte - Juli 2026"
    )
    assert item.session_start is None
    assert item.energy_total_kwh is None
    assert item.net_amount == Decimal("10.0000")
    assert item.vat_amount == Decimal("1.90")
    assert item.gross_amount == Decimal("11.90")

    assert invoice.total_net == Decimal("10.00")
    assert invoice.vat_amount == Decimal("1.90")
    assert invoice.total_gross == Decimal("11.90")

    charge = database_session.scalar(
        select(MonthlyBaseFeeCharge)
    )

    assert charge is not None
    assert charge.rfid_card_id == (
        item.monthly_base_fee_charge.rfid_card_id
    )
    assert charge.fee_month == date(2026, 7, 1)
    assert charge.invoice_id == invoice.id
    assert charge.invoiced is False

    with pytest.raises(
        NoBillableSessionsError
    ):
        create_invoice_draft(
            database_session,
            user_id=user.id,
            service_period_start=datetime(
                2026,
                7,
                1,
            ),
            service_period_end=datetime(
                2026,
                8,
                1,
            ),
        )


def test_zero_base_fee_creates_no_invoice_item(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("0.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

    with pytest.raises(
        NoBillableSessionsError
    ):
        create_invoice_draft(
            database_session,
            user_id=user.id,
            service_period_start=datetime(
                2026,
                7,
                1,
            ),
            service_period_end=datetime(
                2026,
                8,
                1,
            ),
        )

    assert database_session.scalar(
        select(MonthlyBaseFeeCharge.id)
    ) is None


def test_finalizes_monthly_base_fee_charge(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(
            2026,
            7,
            1,
        ),
        service_period_end=datetime(
            2026,
            8,
            1,
        ),
    )

    item = invoice.items[0]
    charge = item.monthly_base_fee_charge

    assert charge is not None
    assert charge.invoice_id == invoice.id
    assert charge.invoiced is False

    finalized_invoice = finalize_invoice(
        database_session,
        invoice_id=invoice.id,
        issue_date=date(2026, 8, 5),
        due_date=date(2026, 8, 5),
    )

    database_session.refresh(charge)

    assert finalized_invoice.status == "finalized"
    assert charge.invoice_id == invoice.id
    assert charge.invoiced is True


def test_rejects_unreserved_monthly_base_fee(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

    invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(
            2026,
            7,
            1,
        ),
        service_period_end=datetime(
            2026,
            8,
            1,
        ),
    )

    charge = (
        invoice.items[0]
        .monthly_base_fee_charge
    )

    assert charge is not None

    charge.invoice_id = None
    database_session.flush()

    with pytest.raises(
        InvoiceItemStateError
    ):
        finalize_invoice(
            database_session,
            invoice_id=invoice.id,
            issue_date=date(2026, 8, 5),
            due_date=date(2026, 8, 5),
        )


def test_cancels_and_rebills_monthly_base_fee(
    database_session: Session,
) -> None:
    user = create_test_data(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.flush()

    original_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(
            2026,
            7,
            1,
        ),
        service_period_end=datetime(
            2026,
            8,
            1,
        ),
    )

    assert len(original_invoice.items) == 1

    original_item = original_invoice.items[0]
    charge = original_item.monthly_base_fee_charge

    assert charge is not None

    original_item_id = original_item.id
    charge_id = charge.id

    finalize_invoice(
        database_session,
        invoice_id=original_invoice.id,
        issue_date=date(2026, 8, 5),
        due_date=date(2026, 8, 5),
    )

    database_session.refresh(charge)

    assert charge.invoiced is True
    assert charge.invoice_id == original_invoice.id

    cancellation = create_cancellation_draft(
        database_session,
        original_invoice_id=original_invoice.id,
        reason="Teststorno Grundgebühr",
    )

    assert len(cancellation.items) == 1

    cancellation_item = cancellation.items[0]

    assert (
        cancellation_item.item_type
        == "monthly_base_fee"
    )
    assert (
        cancellation_item
        .monthly_base_fee_charge_id
        == charge_id
    )
    assert (
        cancellation_item.reversed_invoice_item_id
        == original_item_id
    )
    assert cancellation_item.charging_session_id is None
    assert cancellation_item.session_start is None
    assert cancellation_item.energy_total_kwh is None
    assert cancellation_item.cost_grid_net is None
    assert (
        cancellation_item.net_amount
        == Decimal("-10.0000")
    )
    assert (
        cancellation_item.vat_amount
        == Decimal("-1.90")
    )
    assert (
        cancellation_item.gross_amount
        == Decimal("-11.90")
    )

    finalize_cancellation(
        database_session,
        cancellation_id=cancellation.id,
        issue_date=date(2026, 8, 6),
    )

    database_session.refresh(charge)

    assert charge.invoiced is False
    assert charge.invoice_id is None

    rebill_invoice = create_invoice_draft(
        database_session,
        user_id=user.id,
        service_period_start=datetime(
            2026,
            7,
            1,
        ),
        service_period_end=datetime(
            2026,
            8,
            1,
        ),
    )

    assert len(rebill_invoice.items) == 1

    rebill_item = rebill_invoice.items[0]

    assert rebill_item.item_type == "monthly_base_fee"
    assert (
        rebill_item.monthly_base_fee_charge_id
        == charge_id
    )
    assert (
        rebill_item.rebills_invoice_item_id
        == original_item_id
    )

    charges = list(
        database_session.scalars(
            select(MonthlyBaseFeeCharge)
        ).all()
    )

    assert len(charges) == 1
    assert charges[0].id == charge_id
