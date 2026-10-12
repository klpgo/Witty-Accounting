"""
Automatische Abrechnung: Läufe, Entwürfe, Prüffrist, Finalisierung,
Zustellung und Nachfrage des Kunden.

Alle Zeiten der Tests sind Ortszeit Europe/Berlin (siehe conftest.py).
"""
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.billing_run import (
    RUN_COMPLETED,
    RUN_IN_REVIEW,
    RUN_WAITING_FOR_DATA,
    BillingRun,
)
from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services import auto_billing, billing_email
from app.services.auto_billing import (
    InquiryNotFoundError,
    InquiryStateError,
    check_all_tenants,
    process_tenant,
    request_review_hold,
)
from app.services.invoice_email import (
    InvoiceEmailDeliveryError,
    InvoiceEmailResult,
)
from app.tenancy.context import TenantContext
from app.utils.local_time import LOCAL_TIMEZONE


def at(*args: int) -> datetime:
    """Ortszeit als Zeitpunkt mit Zeitzone (wie der Scheduler ihn liefert)."""
    return datetime(*args, tzinfo=LOCAL_TIMEZONE)


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
                monthly_base_fee_net=Decimal("0.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
                invoice_issuer_name="Witty Test",
                invoice_issuer_address="Testweg 1, 12345 Teststadt",
                invoice_tax_number="12345",
                invoice_payment_term_days=14,
                auto_billing_enabled=True,
                auto_billing_interval="monthly",
                auto_billing_cutoff_day=0,
                auto_billing_grace_days=2,
                auto_billing_review_days=7,
                auto_billing_run_time="06:00",
                invoice_issuer_email="rechnung@example.com",
                auto_billing_active_since=date(2026, 10, 10),
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
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Alle E-Mails abfangen."""
    sent: dict[str, list] = {
        "review": [],
        "waiting": [],
        "drafts": [],
        "finalized": [],
        "inquiry": [],
        "invoice": [],
    }

    monkeypatch.setattr(
        billing_email,
        "send_review_email",
        lambda db, invoice: sent["review"].append(invoice.id) or "x@example.com",
    )
    monkeypatch.setattr(
        billing_email,
        "send_waiting_for_data_email",
        lambda db, **kwargs: sent["waiting"].append(kwargs),
    )
    monkeypatch.setattr(
        billing_email,
        "send_drafts_created_email",
        lambda db, **kwargs: sent["drafts"].append(kwargs),
    )
    monkeypatch.setattr(
        billing_email,
        "send_finalized_email",
        lambda db, **kwargs: sent["finalized"].append(kwargs),
    )
    monkeypatch.setattr(
        billing_email,
        "send_inquiry_email",
        lambda db, **kwargs: sent["inquiry"].append(kwargs),
    )

    def send_invoice_email(db, invoice_id):
        sent["invoice"].append(invoice_id)
        return InvoiceEmailResult(
            recipient_email="x@example.com",
            subject="Rechnung",
        )

    monkeypatch.setattr(auto_billing, "send_invoice_email", send_invoice_email)

    return sent


def add_customer(
    db: Session,
    suffix: str,
    *,
    session_start: datetime | None = datetime(2026, 10, 15, 10, 0),
    post: bool = False,
    address: str | None = "Teststraße 1, 12345 Teststadt",
    valid_from: datetime = datetime(2026, 1, 1),
    valid_to: datetime | None = None,
) -> User:
    user = User(
        email=f"kunde-{suffix}@example.com",
        password_hash="not-used",
        first_name="Kunde",
        last_name=suffix,
        address=address,
        invoice_delivery_email=not post,
        invoice_delivery_post=post,
        active=True,
        is_admin=False,
    )
    card = RFIDCard(
        rfid_number=f"CARD-{suffix}",
        description=f"Karte {suffix}",
        active=True,
    )
    assignment = RFIDCardAssignment(
        rfid_card=card,
        user=user,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add_all([user, card, assignment])

    if session_start is not None:
        db.add(
            ChargingSession(
                station_id="WB1",
                start_time=session_start,
                end_time=session_start.replace(hour=session_start.hour + 1),
                rfid_card=card,
                rfid_assignment=assignment,
                energy_total_kwh=10.0,
                energy_pv_kwh=4.0,
                cost_grid_net=Decimal("1.8000"),
                cost_pv_net=Decimal("0.4000"),
                vat_rate=Decimal("19.00"),
                invoiced=False,
                import_hash=sha256(f"session-{suffix}".encode()).hexdigest(),
                source="xlsx",
            )
        )

    db.commit()
    db.refresh(user)

    return user


def invoices(db: Session) -> list[Invoice]:
    db.expire_all()
    return list(db.scalars(select(Invoice).order_by(Invoice.id)).all())


def runs(db: Session) -> list[BillingRun]:
    db.expire_all()
    return list(
        db.scalars(select(BillingRun).order_by(BillingRun.period_start)).all()
    )


def test_nothing_happens_before_run_time(db: Session, mails) -> None:
    add_customer(db, "a")

    # Stichtag 31.10., zwei Puffertage, 06:00 → 03.11. 06:00
    process_tenant(db, at(2026, 11, 3, 5, 59))

    assert runs(db) == []
    assert invoices(db) == []


def test_disabled_auto_billing_does_nothing(db: Session, mails) -> None:
    db.get(GlobalSettings, 1).auto_billing_enabled = False
    db.commit()
    add_customer(db, "a")

    process_tenant(db, at(2026, 11, 3, 7, 0))

    assert runs(db) == []


def test_creates_drafts_for_customers_with_assignments(
    db: Session,
    mails,
) -> None:
    first = add_customer(db, "a")
    second = add_customer(db, "b", session_start=datetime(2026, 10, 20, 9, 0))
    # Zuordnung endete vor dem Zeitraum: nicht abgerechnet
    add_customer(
        db,
        "c",
        session_start=None,
        valid_to=datetime(2026, 9, 1),
    )
    # Ladevorgang im Folgemonat: gehört nicht in diesen Lauf
    add_customer(db, "d", session_start=datetime(2026, 11, 2, 9, 0))

    process_tenant(db, at(2026, 11, 3, 6, 0))

    [run] = runs(db)
    assert run.period_start == datetime(2026, 10, 1)
    assert run.period_end == datetime(2026, 11, 1)
    assert run.status == RUN_IN_REVIEW
    assert run.drafts_created == 2
    assert run.review_due_date == date(2026, 11, 10)

    drafts = invoices(db)
    assert [invoice.user_id for invoice in drafts] == [first.id, second.id]

    for invoice in drafts:
        assert invoice.status == "draft"
        assert invoice.invoice_number is None
        assert invoice.issue_date is None
        assert invoice.billing_run_id == run.id
        assert invoice.review_status == "in_review"
        assert invoice.review_due_date == date(2026, 11, 10)
        assert invoice.review_notified_at is not None
        assert invoice.service_period_start == datetime(2026, 10, 1)
        assert invoice.service_period_end == datetime(2026, 11, 1)

    assert mails["review"] == [invoice.id for invoice in drafts]
    assert len(mails["drafts"]) == 1
    assert mails["drafts"][0]["created"] == 2


def test_run_is_created_only_once(db: Session, mails) -> None:
    add_customer(db, "a")

    process_tenant(db, at(2026, 11, 3, 6, 0))
    process_tenant(db, at(2026, 11, 3, 6, 10))
    process_tenant(db, at(2026, 11, 4, 6, 0))

    assert len(runs(db)) == 1
    assert len(invoices(db)) == 1
    assert len(mails["review"]) == 1


def test_waits_for_hager_fetch_and_notifies_once(db: Session, mails) -> None:
    settings = db.get(GlobalSettings, 1)
    settings.hager_auto_import_enabled = True
    # letzter Abruf 31.10. 22:00 UTC = 23:00 Ortszeit: Zeitraum noch offen
    settings.hager_last_successful_fetch_at = datetime(2026, 10, 31, 22, 0)
    db.commit()
    add_customer(db, "a")

    process_tenant(db, at(2026, 11, 3, 6, 0))
    process_tenant(db, at(2026, 11, 3, 7, 0))

    [run] = runs(db)
    assert run.status == RUN_WAITING_FOR_DATA
    assert run.waiting_notified_at is not None
    assert invoices(db) == []
    assert len(mails["waiting"]) == 1

    # Abruf nach Mitternacht Ortszeit (31.10. 23:30 UTC = 01.11. 00:30 MEZ)
    settings = db.get(GlobalSettings, 1)
    settings.hager_last_successful_fetch_at = datetime(2026, 10, 31, 23, 30)
    db.commit()

    process_tenant(db, at(2026, 11, 3, 8, 0))

    [run] = runs(db)
    assert run.status == RUN_IN_REVIEW
    assert len(invoices(db)) == 1


def test_skips_customer_with_existing_draft(db: Session, mails) -> None:
    from app.services.invoicing import create_invoice_draft

    user = add_customer(db, "a")
    manual = create_invoice_draft(
        db,
        user_id=user.id,
        service_period_start=datetime(2026, 10, 1),
        service_period_end=datetime(2026, 11, 1),
    )

    process_tenant(db, at(2026, 11, 3, 6, 0))

    [run] = runs(db)
    assert run.status == RUN_COMPLETED
    assert run.drafts_created == 0
    assert '"existing_draft"' in run.details
    assert f'"invoice_id": {manual.id}' in run.details
    assert [invoice.id for invoice in invoices(db)] == [manual.id]
    assert mails["review"] == []


def test_reports_customer_without_address(db: Session, mails) -> None:
    add_customer(db, "a", address=None)
    add_customer(db, "b")

    process_tenant(db, at(2026, 11, 3, 6, 0))

    [run] = runs(db)
    assert run.drafts_created == 1
    assert "No address" in run.details
    skipped = mails["drafts"][0]["skipped"]
    assert len(skipped) == 1
    assert skipped[0].label == "Kunde a"


def test_finalizes_after_review_period(db: Session, mails) -> None:
    add_customer(db, "a")
    add_customer(db, "b", post=True)

    process_tenant(db, at(2026, 11, 3, 6, 0))
    first, second = invoices(db)

    # Prüffrist bis 10.11.: am Vortag und vor 06:00 noch nichts
    process_tenant(db, at(2026, 11, 9, 23, 0))
    process_tenant(db, at(2026, 11, 10, 5, 59))
    assert all(invoice.status == "draft" for invoice in invoices(db))

    process_tenant(db, at(2026, 11, 10, 6, 0))

    first, second = invoices(db)

    for invoice in (first, second):
        assert invoice.status == "finalized"
        assert invoice.issue_date == date(2026, 11, 10)
        assert invoice.due_date == date(2026, 11, 24)
        assert invoice.invoice_number == f"RE-2026-{invoice.id:06d}"
        assert invoice.pdf_storage_path is not None

    assert first.delivery_status == "sent"
    assert second.delivery_status == "postal"
    assert mails["invoice"] == [first.id]

    [summary] = mails["finalized"]
    assert summary["finalized_count"] == 2
    assert [entry.label for entry in summary["postal"]] == [
        f"{second.invoice_number} Kunde b"
    ]

    [run] = runs(db)
    assert run.status == RUN_COMPLETED


def test_inquiry_puts_draft_on_hold(db: Session, mails) -> None:
    user = add_customer(db, "a")
    process_tenant(db, at(2026, 11, 3, 6, 0))
    [draft] = invoices(db)

    invoice, contact = request_review_hold(db, invoice_id=draft.id, user=user)

    assert invoice.review_status == "on_hold"
    assert invoice.inquiry_at is not None
    assert contact == "rechnung@example.com"
    assert len(mails["inquiry"]) == 1

    # zweite Nachfrage: keine weitere E-Mail
    request_review_hold(db, invoice_id=draft.id, user=user)
    assert len(mails["inquiry"]) == 1

    process_tenant(db, at(2026, 11, 10, 6, 0))

    [draft] = invoices(db)
    assert draft.status == "draft"
    assert draft.review_status == "on_hold"
    assert mails["finalized"] == []

    [run] = runs(db)
    assert run.status == RUN_IN_REVIEW


def test_inquiry_only_for_own_review_draft(db: Session, mails) -> None:
    owner = add_customer(db, "a")
    other = add_customer(db, "b")
    process_tenant(db, at(2026, 11, 3, 6, 0))
    owner_draft = invoices(db)[0]

    with pytest.raises(InquiryNotFoundError):
        request_review_hold(db, invoice_id=owner_draft.id, user=other)

    process_tenant(db, at(2026, 11, 10, 6, 0))
    owner_invoice = db.get(Invoice, owner_draft.id)
    assert owner_invoice.status == "finalized"

    # nach der Finalisierung keine Nachfrage mehr
    with pytest.raises(InquiryNotFoundError):
        request_review_hold(db, invoice_id=owner_invoice.id, user=owner)


def test_inquiry_rejected_after_failed_finalization(db: Session, mails) -> None:
    user = add_customer(db, "a")
    process_tenant(db, at(2026, 11, 3, 6, 0))
    [draft] = invoices(db)
    draft.review_status = "failed"
    db.commit()

    with pytest.raises(InquiryStateError):
        request_review_hold(db, invoice_id=draft.id, user=user)


def test_failed_review_email_blocks_finalization_and_is_retried(
    db: Session,
    mails,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_customer(db, "a")
    attempts: list[int] = []

    def failing_review_email(db, invoice):
        attempts.append(invoice.id)
        raise InvoiceEmailDeliveryError("SMTP down")

    monkeypatch.setattr(billing_email, "send_review_email", failing_review_email)

    process_tenant(db, at(2026, 11, 3, 6, 0))
    [draft] = invoices(db)
    assert draft.review_notified_at is None
    assert draft.notification_attempts == 1
    assert draft.notification_error == "SMTP down"
    assert len(mails["drafts"][0]["notify_failed"]) == 1

    # nicht zugestellte Prüf-E-Mail: keine automatische Finalisierung
    process_tenant(db, at(2026, 11, 10, 6, 0))
    [draft] = invoices(db)
    assert draft.status == "draft"
    assert draft.notification_attempts == 2

    for _ in range(10):
        process_tenant(db, at(2026, 11, 10, 7, 0))

    [draft] = invoices(db)
    assert draft.notification_attempts == auto_billing.MAX_NOTIFICATION_ATTEMPTS
    assert len(attempts) == auto_billing.MAX_NOTIFICATION_ATTEMPTS


def test_failed_delivery_is_retried(
    db: Session,
    mails,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_customer(db, "a")
    process_tenant(db, at(2026, 11, 3, 6, 0))

    calls: list[int] = []

    def flaky_send(db, invoice_id):
        calls.append(invoice_id)

        if len(calls) == 1:
            raise InvoiceEmailDeliveryError("SMTP down")

        return InvoiceEmailResult(recipient_email="x", subject="y")

    monkeypatch.setattr(auto_billing, "send_invoice_email", flaky_send)

    process_tenant(db, at(2026, 11, 10, 6, 0))
    [invoice] = invoices(db)
    assert invoice.status == "finalized"
    assert invoice.delivery_status == "failed"
    assert invoice.notification_error == "SMTP down"
    assert len(mails["finalized"][0]["failed"]) == 1

    process_tenant(db, at(2026, 11, 10, 6, 10))
    [invoice] = invoices(db)
    assert invoice.delivery_status == "sent"
    assert invoice.notification_error is None
    assert len(calls) == 2


def test_first_period_starts_at_activation(db: Session, mails) -> None:
    # eingeschaltet am 10.10.: erster Stichtag ist der 31.10., nicht der 30.09.
    add_customer(db, "a", session_start=datetime(2026, 9, 15, 10, 0))

    process_tenant(db, at(2026, 10, 12, 7, 0))

    assert runs(db) == []


def test_missed_periods_are_caught_up_in_order(db: Session, mails) -> None:
    add_customer(db, "a")
    add_customer(db, "b", session_start=datetime(2026, 11, 15, 10, 0))

    # Server war bis Mitte Dezember aus
    process_tenant(db, at(2026, 12, 15, 7, 0))
    process_tenant(db, at(2026, 12, 15, 7, 10))

    assert [(run.period_start, run.period_end) for run in runs(db)] == [
        (datetime(2026, 10, 1), datetime(2026, 11, 1)),
        (datetime(2026, 11, 1), datetime(2026, 12, 1)),
    ]
    assert len(invoices(db)) == 2


def test_check_all_tenants_throttles_and_isolates(db: Session, mails) -> None:
    tenants = [
        TenantContext(
            id=tenant_id,
            slug=f"mandant-{tenant_id}",
            name=f"Mandant {tenant_id}",
            db_host="localhost",
            db_port=3306,
            db_name=f"db{tenant_id}",
            db_user="user",
            db_password="secret",
        )
        for tenant_id in (1, 2)
    ]
    processed: list[int] = []

    def session_factory(tenant):
        if tenant.id == 1:
            raise RuntimeError("database unavailable")

        processed.append(tenant.id)
        return db

    auto_billing._last_checks.clear()
    auto_billing._running_tenants.clear()

    def run_now(fn, *args):
        fn(*args)

    now = at(2026, 11, 3, 6, 0)
    assert check_all_tenants(now, lambda: tenants, session_factory, run_now) == 2
    assert processed == [2]

    # innerhalb des Prüfintervalls keine erneute Prüfung
    assert check_all_tenants(
        at(2026, 11, 3, 6, 5), lambda: tenants, session_factory, run_now
    ) == 0
    assert check_all_tenants(
        at(2026, 11, 3, 6, 11), lambda: tenants, session_factory, run_now
    ) == 2


def test_weekly_run_bills_prorated_base_fee(db: Session, mails) -> None:
    settings = db.get(GlobalSettings, 1)
    settings.monthly_base_fee_net = Decimal("31.0000")
    settings.auto_billing_interval = "weekly"
    settings.auto_billing_cutoff_day = 7
    db.commit()
    add_customer(db, "a", session_start=None)

    # Woche 05.10.–11.10. (Stichtag Sonntag), Erstellung 14.10. 06:00
    process_tenant(db, at(2026, 10, 14, 6, 0))

    [run] = runs(db)
    assert run.period_start == datetime(2026, 10, 5)
    assert run.period_end == datetime(2026, 10, 12)

    [invoice] = invoices(db)
    [fee] = [item for item in invoice.items if item.item_type == "monthly_base_fee"]
    assert fee.net_amount == Decimal("7")
    assert "(anteilig 7/31 Tage)" in fee.description
