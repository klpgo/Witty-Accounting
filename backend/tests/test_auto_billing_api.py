from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
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
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services import billing_email
from app.services.invoicing import create_invoice_draft


ADMIN = User(
    id=0,
    email="admin@example.com",
    password_hash="not-used",
    first_name="Admin",
    last_name="Test",
    invoice_delivery_email=False,
    invoice_delivery_post=False,
    active=True,
    is_admin=True,
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
                monthly_base_fee_net=Decimal("0.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
                invoice_issuer_name="Witty Test",
                invoice_issuer_address="Testweg 1, 12345 Teststadt",
                invoice_tax_number="12345",
                invoice_payment_term_days=14,
                auto_billing_notification_email="rechnung@example.com",
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
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: ADMIN

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_mails(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []
    monkeypatch.setattr(
        billing_email,
        "send_inquiry_email",
        lambda db, **kwargs: sent.append(kwargs),
    )
    return sent


def add_customer(db: Session, suffix: str) -> User:
    user = User(
        email=f"kunde-{suffix}@example.com",
        password_hash="not-used",
        first_name="Kunde",
        last_name=suffix,
        address="Teststraße 1, 12345 Teststadt",
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=False,
    )
    card = RFIDCard(rfid_number=f"CARD-{suffix}", active=True)
    assignment = RFIDCardAssignment(
        rfid_card=card,
        user=user,
        valid_from=datetime(2026, 1, 1),
    )
    session = ChargingSession(
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
        import_hash=f"{suffix:0>64}"[-64:],
        source="xlsx",
    )
    db.add_all([user, card, assignment, session])
    db.commit()
    db.refresh(user)

    return user


def make_draft(db: Session, user: User, *, review: bool) -> int:
    invoice = create_invoice_draft(
        db,
        user_id=user.id,
        service_period_start=datetime(2026, 10, 1),
        service_period_end=datetime(2026, 11, 1),
    )

    if review:
        invoice.review_status = "in_review"
        invoice.review_due_date = date(2026, 11, 10)
        invoice.notification_error = "internal detail"
        db.commit()

    return invoice.id


def as_user(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def test_customer_sees_review_draft_but_not_manual_draft(
    client: TestClient,
    db: Session,
) -> None:
    reviewed = add_customer(db, "a")
    manual = add_customer(db, "b")
    review_id = make_draft(db, reviewed, review=True)
    manual_id = make_draft(db, manual, review=False)

    as_user(reviewed)
    listed = client.get("/api/invoices").json()
    assert [invoice["id"] for invoice in listed] == [review_id]
    assert listed[0]["review_status"] == "in_review"
    assert listed[0]["review_contact_email"] == "rechnung@example.com"
    assert listed[0]["notification_error"] is None

    detail = client.get(f"/api/invoices/{review_id}")
    assert detail.status_code == 200
    assert detail.json()["review_due_date"] == "2026-11-10"

    as_user(manual)
    assert client.get("/api/invoices").json() == []
    assert client.get(f"/api/invoices/{manual_id}").status_code == 404
    assert client.get(f"/api/invoices/{review_id}").status_code == 404


def test_admin_sees_notification_error(client: TestClient, db: Session) -> None:
    review_id = make_draft(db, add_customer(db, "a"), review=True)

    detail = client.get(f"/api/invoices/{review_id}").json()

    assert detail["notification_error"] == "internal detail"


def test_draft_pdf(client: TestClient, db: Session) -> None:
    owner = add_customer(db, "a")
    other = add_customer(db, "b")
    review_id = make_draft(db, owner, review=True)

    as_user(owner)
    response = client.get(f"/api/invoices/{review_id}/draft-pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

    text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
    assert "Ladestromrechnung – Entwurf" in text
    assert "Zahlungsziel: 14 Tage ab Rechnungsdatum" in text
    assert "Girocode" not in text

    as_user(other)
    assert client.get(f"/api/invoices/{review_id}/draft-pdf").status_code == 404


def test_draft_pdf_rejects_finalized_invoice(
    client: TestClient,
    db: Session,
) -> None:
    invoice_id = make_draft(db, add_customer(db, "a"), review=False)
    client.post(
        f"/api/invoices/{invoice_id}/finalize",
        json={"issue_date": "2026-11-10"},
    )

    response = client.get(f"/api/invoices/{invoice_id}/draft-pdf")

    assert response.status_code == 409


def test_inquiry_endpoint(
    client: TestClient,
    db: Session,
    no_mails: list[dict],
) -> None:
    owner = add_customer(db, "a")
    other = add_customer(db, "b")
    review_id = make_draft(db, owner, review=True)
    manual_id = make_draft(db, other, review=False)

    as_user(other)
    assert client.post(f"/api/invoices/{review_id}/inquiry").status_code == 404
    assert client.post(f"/api/invoices/{manual_id}/inquiry").status_code == 404

    as_user(owner)
    response = client.post(f"/api/invoices/{review_id}/inquiry")

    assert response.status_code == 200
    body = response.json()
    assert body["contact_email"] == "rechnung@example.com"
    assert body["invoice"]["review_status"] == "on_hold"
    assert body["invoice"]["inquiry_at"] is not None
    assert len(no_mails) == 1
    assert no_mails[0]["contact_email"] == "rechnung@example.com"


def test_settings_enable_sets_activation_date(client: TestClient) -> None:
    response = client.get("/api/settings/auto-billing")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["next_run_at"] is None

    response = client.patch(
        "/api/settings/auto-billing",
        json={
            "enabled": True,
            "interval": "monthly",
            "cutoff_day": 0,
            "grace_days": 3,
            "review_days": 5,
            "run_time": "07:30",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["active_since"] is not None
    assert body["grace_days"] == 3
    assert body["review_days"] == 5
    assert body["run_time"] == "07:30"
    assert body["next_period_start"] is not None
    assert body["next_run_at"] is not None
    assert body["effective_notification_email"] == "rechnung@example.com"


def test_settings_validate_cutoff_day(client: TestClient) -> None:
    response = client.patch(
        "/api/settings/auto-billing",
        json={"interval": "weekly", "cutoff_day": 0},
    )
    assert response.status_code == 422

    # Wechsel ohne Stichtag: passender Standard (Sonntag)
    response = client.patch(
        "/api/settings/auto-billing",
        json={"interval": "weekly"},
    )
    assert response.status_code == 200
    assert response.json()["cutoff_day"] == 7

    response = client.patch(
        "/api/settings/auto-billing",
        json={"run_time": "25:00"},
    )
    assert response.status_code == 422

    response = client.patch(
        "/api/settings/auto-billing",
        json={"notification_email": "keine-adresse"},
    )
    assert response.status_code == 422


def test_settings_require_notification_address(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "mail_from_address", "")
    response = client.patch(
        "/api/settings/auto-billing",
        json={"enabled": True, "notification_email": ""},
    )

    assert response.status_code == 422
    assert db.get(GlobalSettings, 1).auto_billing_enabled is False


def test_preview_lists_customers(client: TestClient, db: Session) -> None:
    first = add_customer(db, "a")
    second = add_customer(db, "b")
    make_draft(db, second, review=False)

    response = client.get("/api/settings/auto-billing/preview")

    assert response.status_code == 200
    body = response.json()
    customers = {customer["user_id"]: customer for customer in body["customers"]}
    assert set(customers) == {first.id, second.id}
    assert customers[first.id]["delivery"] == "email"
    assert customers[first.id]["existing_draft_id"] is None
    assert body["data_ready"] is True


def test_settings_list_runs_with_current_names(
    client: TestClient,
    db: Session,
) -> None:
    from app.models.billing_run import BillingRun

    user = add_customer(db, "a")
    db.add(
        BillingRun(
            period_start=datetime(2026, 10, 1),
            period_end=datetime(2026, 11, 1),
            cutoff_date=date(2026, 10, 31),
            interval="monthly",
            status="completed",
            details=(
                f'[{{"user_id": {user.id}, "reason": "existing_draft", '
                '"invoice_id": 7}, {"user_id": 999, "reason": "error", '
                '"message": "No address is stored for the invoice recipient."}]'
            ),
        )
    )
    db.commit()

    [run] = client.get("/api/settings/auto-billing").json()["runs"]

    assert run["status"] == "completed"
    assert [entry["name"] for entry in run["skipped"]] == ["Kunde a", "#999"]
    assert run["skipped"][0]["invoice_id"] == 7
