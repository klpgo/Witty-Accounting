from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import require_admin
from app.database import Base
from app.main import app
from app.models.charging_session import (
    ChargingSession,
)
from app.models.energy_price import EnergyPrice
from app.models.rfid_card import RFIDCard
from app.models.user import User

from hashlib import sha256
from pathlib import Path

from app.config import settings
from app.models.invoice import Invoice


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


@pytest.fixture
def client(
    database_session: Session,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[
        Session,
        None,
        None,
    ]:
        yield database_session

    def override_require_admin() -> None:
        return None

    app.dependency_overrides[get_db] = (
        override_get_db
    )
    app.dependency_overrides[
        require_admin
    ] = override_require_admin

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_billable_session(
    db: Session,
) -> tuple[User, ChargingSession]:
    user = User(
        email="billing@example.com",
        password_hash="not-used",
        salutation=None,
        first_name="Billing",
        last_name="User",
        address="Teststraße 1, 12345 Teststadt",
        phone=None,
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=False,
    )

    card = RFIDCard(
        user=user,
        rfid_number="BILLING-CARD",
        description="Rechnungstest",
        active=True,
    )

    session = ChargingSession(
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
        invoiced=False,
        invoice_id=None,
        import_hash="k" * 64,
        source="xlsx",
    )

    db.add(
        EnergyPrice(
            valid_from=datetime(2026, 1, 1),
            grid_price_net=Decimal("0.3000"),
            pv_price_net=Decimal("0.1000"),
            vat_rate=Decimal("19.00"),
        )
    )
    db.add_all([user, session])
    db.commit()
    db.refresh(user)
    db.refresh(session)

    return user, session


def test_creates_invoice_draft(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["status"] == "draft"
    assert body["invoice_number"] is None
    assert body["total_net"] == "2.20"
    assert body["vat_amount"] == "0.42"
    assert body["total_gross"] == "2.62"
    assert len(body["items"]) == 1
    assert body["items"][0][
        "energy_grid_kwh"
    ] == "6.0000"


def test_finalizes_invoice(
    client: TestClient,
    database_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        tmp_path,
    )

    user, charging_session = (
        create_billable_session(
            database_session
        )
    )

    draft_response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    invoice_id = draft_response.json()["id"]

    response = client.post(
        f"/invoices/{invoice_id}/finalize",
        json={
            "issue_date": "2026-07-05",
        },
    )

    body = response.json()

    invoice = database_session.get(
        Invoice,
        invoice_id,
    )

    assert invoice is not None
    assert invoice.pdf_storage_path == (
        f"2026/{body['invoice_number']}.pdf"
    )
    assert invoice.pdf_sha256 is not None
    assert invoice.pdf_size_bytes is not None
    assert invoice.pdf_created_at is not None

    pdf_path = (
        tmp_path / invoice.pdf_storage_path
    )

    assert pdf_path.is_file()

    pdf_bytes = pdf_path.read_bytes()

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) == (
        invoice.pdf_size_bytes
    )
    assert sha256(pdf_bytes).hexdigest() == (
        invoice.pdf_sha256
    )

    assert response.status_code == 200

    assert body["status"] == "finalized"
    assert body["issue_date"] == "2026-07-05"
    assert body["invoice_number"] == (
        f"RE-2026-{invoice_id:06d}"
    )

    database_session.refresh(
        charging_session
    )

    assert charging_session.invoiced is True
    assert charging_session.invoice_id == invoice_id


def test_lists_and_reads_invoices(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    create_response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    invoice_id = create_response.json()["id"]

    list_response = client.get("/invoices")
    detail_response = client.get(
        f"/invoices/{invoice_id}"
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == invoice_id


def test_rejects_unknown_invoice_user(
    client: TestClient,
) -> None:
    response = client.post(
        "/invoices/drafts",
        json={
            "user_id": 999999,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    assert response.status_code == 404


def test_downloads_archived_invoice_pdf(
    client: TestClient,
    database_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        tmp_path,
    )

    user, _ = create_billable_session(
        database_session
    )

    draft_response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    invoice_id = draft_response.json()["id"]

    finalize_response = client.post(
        f"/invoices/{invoice_id}/finalize",
        json={
            "issue_date": "2026-07-05",
            "due_date": "2026-07-19",
        },
    )

    assert finalize_response.status_code == 200

    response = client.get(
        f"/invoices/{invoice_id}/pdf"
    )

    assert response.status_code == 200
    assert response.headers[
        "content-type"
    ].startswith("application/pdf")
    assert "attachment" in response.headers[
        "content-disposition"
    ]
    assert response.content.startswith(b"%PDF-")

    invoice = database_session.get(
        Invoice,
        invoice_id,
    )

    assert invoice is not None
    assert sha256(
        response.content
    ).hexdigest() == invoice.pdf_sha256


def test_pdf_download_rejects_unarchived_draft(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    draft_response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-06-01T00:00:00"
            ),
            "service_period_end": (
                "2026-07-01T00:00:00"
            ),
        },
    )

    invoice_id = draft_response.json()["id"]

    response = client.get(
        f"/invoices/{invoice_id}/pdf"
    )

    assert response.status_code == 409
