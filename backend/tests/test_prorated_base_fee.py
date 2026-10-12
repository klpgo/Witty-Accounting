"""
Anteilige Grundgebühr (prorate_base_fee=True), z. B. bei wöchentlicher
automatischer Abrechnung: jeder Monat, der den Leistungszeitraum schneidet,
wird für die Tage im Zeitraum berechnet (Grundgebühr × Tage / Monatstage).

Grundgebühr in den Tests: 31,00 € netto → im Oktober 1,00 € pro Tag.
"""
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice, InvoiceItem
from app.models.monthly_base_fee_charge import MonthlyBaseFeeCharge
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services.invoice_cancellation import (
    create_cancellation_draft,
    finalize_cancellation,
)
from app.services.invoicing import (
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
)


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
                monthly_base_fee_net=Decimal("31.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
                invoice_issuer_name="Witty Test",
                invoice_issuer_address="Testweg 1, 12345 Teststadt",
                invoice_tax_number="12345",
            )
        )
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(
    db: Session,
    *,
    valid_from: datetime = datetime(2026, 1, 1),
    valid_to: datetime | None = None,
) -> User:
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
    card = RFIDCard(rfid_number="CARD-1", description="Karte 1", active=True)
    db.add_all(
        [
            user,
            card,
            RFIDCardAssignment(
                rfid_card=card,
                user=user,
                valid_from=valid_from,
                valid_to=valid_to,
            ),
        ]
    )
    db.commit()
    db.refresh(user)

    return user


def draft(
    db: Session,
    user: User,
    start: datetime,
    end: datetime,
    *,
    prorate: bool = True,
) -> Invoice:
    return create_invoice_draft(
        db,
        user_id=user.id,
        service_period_start=start,
        service_period_end=end,
        prorate_base_fee=prorate,
    )


def fees(invoice: Invoice) -> list[tuple[str, Decimal]]:
    return [
        (item.description, item.net_amount)
        for item in invoice.items
        if item.item_type == "monthly_base_fee"
    ]


def test_weeks_of_a_month_add_up_to_the_monthly_fee(db: Session) -> None:
    user = add_user(db)
    total = Decimal("0")

    weeks = [
        (datetime(2026, 10, 1), datetime(2026, 10, 5)),
        (datetime(2026, 10, 5), datetime(2026, 10, 12)),
        (datetime(2026, 10, 12), datetime(2026, 10, 19)),
        (datetime(2026, 10, 19), datetime(2026, 10, 26)),
        (datetime(2026, 10, 26), datetime(2026, 11, 1)),
    ]

    for start, end in weeks:
        invoice = draft(db, user, start, end)
        [(description, amount)] = fees(invoice)
        days = (end - start).days
        assert amount == Decimal(days)
        assert f"(anteilig {days}/31 Tage)" in description
        finalize_invoice(db, invoice_id=invoice.id, issue_date=end.date())
        total += amount

    assert total == Decimal("31")


def test_week_across_two_months(db: Session) -> None:
    user = add_user(db)

    invoice = draft(db, user, datetime(2026, 9, 28), datetime(2026, 10, 5))

    assert fees(invoice) == [
        (
            "Monatsgebühr Ladekarte Karte 1 - September 2026 "
            "(anteilig 3/30 Tage)",
            Decimal("3.1000"),
        ),
        (
            "Monatsgebühr Ladekarte Karte 1 - Oktober 2026 "
            "(anteilig 4/31 Tage)",
            Decimal("4.0000"),
        ),
    ]


def test_assignment_starting_mid_week(db: Session) -> None:
    user = add_user(db, valid_from=datetime(2026, 10, 15))

    with pytest.raises(NoBillableSessionsError):
        draft(db, user, datetime(2026, 10, 5), datetime(2026, 10, 12))

    invoice = draft(db, user, datetime(2026, 10, 12), datetime(2026, 10, 19))

    [(_, amount)] = fees(invoice)
    assert amount == Decimal("4")


def test_calendar_month_is_unchanged(db: Session) -> None:
    user = add_user(db)

    prorated = draft(db, user, datetime(2026, 10, 1), datetime(2026, 11, 1))

    assert fees(prorated) == [
        ("Monatsgebühr Ladekarte Karte 1 - Oktober 2026", Decimal("31.0000"))
    ]


def test_week_after_full_month_invoice_bills_nothing(db: Session) -> None:
    user = add_user(db)
    month = draft(
        db,
        user,
        datetime(2026, 10, 1),
        datetime(2026, 11, 1),
        prorate=False,
    )
    finalize_invoice(db, invoice_id=month.id, issue_date=date(2026, 11, 2))

    with pytest.raises(NoBillableSessionsError):
        draft(db, user, datetime(2026, 10, 12), datetime(2026, 10, 19))


def test_full_month_after_weeks_bills_only_remaining_days(db: Session) -> None:
    user = add_user(db)

    for start, end in [
        (datetime(2026, 10, 5), datetime(2026, 10, 12)),
        (datetime(2026, 10, 12), datetime(2026, 10, 19)),
    ]:
        invoice = draft(db, user, start, end)
        finalize_invoice(db, invoice_id=invoice.id, issue_date=end.date())

    month = draft(
        db,
        user,
        datetime(2026, 10, 1),
        datetime(2026, 11, 1),
        prorate=False,
    )

    [(description, amount)] = fees(month)
    assert amount == Decimal("17")
    assert "(anteilig 17/31 Tage)" in description


def test_open_week_draft_blocks_its_days(db: Session) -> None:
    user = add_user(db)
    draft(db, user, datetime(2026, 10, 5), datetime(2026, 10, 12))

    month = draft(
        db,
        user,
        datetime(2026, 10, 1),
        datetime(2026, 11, 1),
        prorate=False,
    )

    [(_, amount)] = fees(month)
    assert amount == Decimal("24")


def test_deleted_week_draft_leaves_no_stale_charge(db: Session) -> None:
    user = add_user(db)
    week = draft(db, user, datetime(2026, 10, 5), datetime(2026, 10, 12))

    # wie DELETE /invoices/{id}: Grundgebühr freigeben, Entwurf löschen
    for charge in db.scalars(
        select(MonthlyBaseFeeCharge).where(
            MonthlyBaseFeeCharge.invoice_id == week.id
        )
    ).all():
        charge.invoice_id = None
    db.flush()
    db.delete(week)
    db.commit()

    month = draft(
        db,
        user,
        datetime(2026, 10, 1),
        datetime(2026, 11, 1),
        prorate=False,
    )

    [(_, amount)] = fees(month)
    assert amount == Decimal("31")
    assert db.scalar(
        select(MonthlyBaseFeeCharge.id).where(
            MonthlyBaseFeeCharge.slice_start == date(2026, 10, 5)
        )
    ) is None


def test_cancelled_week_is_rebilled_with_the_same_period(db: Session) -> None:
    user = add_user(db)
    week = draft(db, user, datetime(2026, 10, 5), datetime(2026, 10, 12))
    finalize_invoice(db, invoice_id=week.id, issue_date=date(2026, 10, 13))
    cancellation = create_cancellation_draft(
        db,
        original_invoice_id=week.id,
        reason="Korrektur",
    )
    finalize_cancellation(
        db,
        cancellation_id=cancellation.id,
        issue_date=date(2026, 10, 14),
    )

    # die stornierte Woche bleibt für einen anderen Zeitraum belegt …
    month = draft(
        db,
        user,
        datetime(2026, 10, 1),
        datetime(2026, 11, 1),
        prorate=False,
    )
    [(_, amount)] = fees(month)
    assert amount == Decimal("24")

    # … und wird mit genau diesem Zeitraum neu abgerechnet
    rebill = draft(db, user, datetime(2026, 10, 5), datetime(2026, 10, 12))

    [item] = [
        item for item in rebill.items if item.item_type == "monthly_base_fee"
    ]
    assert item.net_amount == Decimal("7")
    original_item = db.scalar(
        select(InvoiceItem).where(
            InvoiceItem.invoice_id == week.id,
            InvoiceItem.item_type == "monthly_base_fee",
        )
    )
    assert item.rebills_invoice_item_id == original_item.id
