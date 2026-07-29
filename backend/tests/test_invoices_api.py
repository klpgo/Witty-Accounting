from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal

import pytest

from pypdf import PdfReader

from pathlib import Path

from hashlib import sha256

from app.config import settings

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import require_admin
from app.database import Base
from app.main import app
from app.models.global_settings import GlobalSettings
from app.models.charging_session import (
    ChargingSession,
)
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.models.energy_price import EnergyPrice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User

from app.models.invoice import Invoice, InvoiceItem

from app.services.invoicing import create_invoice_draft


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
        rfid_number="BILLING-CARD",
        description="Rechnungstest",
        active=True,
    )

    assignment = RFIDCardAssignment(
        rfid_card=card,
        user=user,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
        valid_to=None,
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
        rfid_assignment=assignment,
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
    db.add_all(
        [
            user,
            card,
            assignment,
            session,
        ]
    )
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


def test_creates_base_fee_only_draft_via_api(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.commit()

    response = client.post(
        "/invoices/drafts",
        json={
            "user_id": user.id,
            "service_period_start": (
                "2026-07-01T00:00:00"
            ),
            "service_period_end": (
                "2026-08-01T00:00:00"
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["status"] == "draft"
    assert body["total_net"] == "10.00"
    assert body["vat_amount"] == "1.90"
    assert body["total_gross"] == "11.90"
    assert len(body["items"]) == 1

    item = body["items"][0]

    assert item["item_type"] == "monthly_base_fee"
    assert item["monthly_base_fee_charge_id"] is not None
    assert item["charging_session_id"] is None
    assert item["description"] == (
        "Monatliche Grundgebühr RFID-Karte "
        "BILLING-CARD – Juli 2026"
    )
    assert item["session_start"] is None
    assert item["session_end"] is None
    assert item["station_id"] is None
    assert item["energy_total_kwh"] is None
    assert item["energy_grid_kwh"] is None
    assert item["energy_pv_kwh"] is None
    assert item["grid_price_net"] is None
    assert item["pv_price_net"] is None
    assert item["cost_grid_net"] is None
    assert item["cost_pv_net"] is None
    assert item["net_amount"] == "10.0000"
    assert item["vat_rate"] == "19.00"
    assert item["vat_amount"] == "1.90"
    assert item["gross_amount"] == "11.90"


def test_create_draft_rejects_missing_recipient_address(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    user.address = None
    database_session.commit()

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

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Für den Rechnungsempfänger "
            "ist keine Anschrift hinterlegt."
        ),
    }


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


def test_creates_cancellation_draft(
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

    assert draft_response.status_code == 201

    original_invoice_id = (
        draft_response.json()["id"]
    )

    finalize_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/finalize"
        ),
        json={
            "issue_date": "2026-07-05",
        },
    )

    assert finalize_response.status_code == 200

    original_body = finalize_response.json()

    response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/cancellations"
        ),
        json={
            "reason": "Fehlerhafte Abrechnung",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["document_type"] == "cancellation"
    assert body["status"] == "draft"
    assert body["invoice_number"] is None

    assert body["original_invoice_id"] == (
        original_invoice_id
    )
    assert body["cancellation_reason"] == (
        "Fehlerhafte Abrechnung"
    )
    assert body["cancelled_at"] is None

    assert len(body["items"]) == 1

    item = body["items"][0]

    assert item["charging_session_id"] is None
    assert (
        item["reversed_invoice_item_id"]
        == original_body["items"][0]["id"]
    )

    assert float(body["total_net"]) == (
        -float(original_body["total_net"])
    )
    assert float(body["vat_amount"]) == (
        -float(original_body["vat_amount"])
    )
    assert float(body["total_gross"]) == (
        -float(original_body["total_gross"])
    )


def test_rejects_second_cancellation_draft(
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

    assert draft_response.status_code == 201

    original_invoice_id = (
        draft_response.json()["id"]
    )

    finalize_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/finalize"
        ),
        json={
            "issue_date": "2026-07-05",
        },
    )

    assert finalize_response.status_code == 200

    first_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/cancellations"
        ),
        json={
            "reason": "Fehlerhafte Abrechnung",
        },
    )

    assert first_response.status_code == 201

    second_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/cancellations"
        ),
        json={
            "reason": "Zweiter Stornoversuch",
        },
    )

    assert second_response.status_code == 409
    assert "existiert bereits" in (
        second_response.json()["detail"]
    )


def test_rejects_cancellation_of_draft_invoice(
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

    assert draft_response.status_code in {
        200,
        201,
    }

    invoice_id = draft_response.json()["id"]

    response = client.post(
        f"/invoices/{invoice_id}/cancellations",
        json={
            "reason": "Unzulässiger Stornoversuch",
        },
    )

    assert response.status_code == 409
    assert "Nur eine finalisierte Rechnung" in (
        response.json()["detail"]
    )

def test_rejects_cancellation_for_missing_invoice(
    client: TestClient,
) -> None:
    response = client.post(
        "/invoices/999999/cancellations",
        json={
            "reason": "Nicht vorhandene Rechnung",
        },
    )

    assert response.status_code == 404
    assert "wurde nicht gefunden" in (
        response.json()["detail"]
    )


def test_finalizes_cancellation_draft(
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

    assert draft_response.status_code in {
        200,
        201,
    }

    original_invoice_id = (
        draft_response.json()["id"]
    )

    original_finalize_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/finalize"
        ),
        json={
            "issue_date": "2026-07-05",
        },
    )

    assert original_finalize_response.status_code == 200

    cancellation_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/cancellations"
        ),
        json={
            "reason": "Fehlerhafte Abrechnung",
        },
    )

    assert cancellation_response.status_code == 201

    cancellation_id = (
        cancellation_response.json()["id"]
    )

    response = client.post(
        (
            f"/invoices/{cancellation_id}"
            "/cancellation/finalize"
        ),
        json={
            "issue_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    database_session.refresh(
        charging_session
    )

    assert charging_session.invoiced is False
    assert charging_session.invoice_id is None

    body = response.json()

    assert body["id"] == cancellation_id
    assert body["document_type"] == "cancellation"
    assert body["status"] == "finalized"
    assert body["invoice_number"] == (
        "ST-2026-000001"
    )
    assert body["issue_date"] == "2026-07-06"
    assert body["due_date"] is None
    assert body["finalized_at"] is not None
    assert body["cancelled_at"] is not None

    assert body["pdf_storage_path"] == (
        "2026/ST-2026-000001.pdf"
    )
    assert body["pdf_sha256"] is not None
    assert body["pdf_size_bytes"] is not None
    assert body["pdf_created_at"] is not None

    pdf_path = (
        tmp_path / body["pdf_storage_path"]
    )

    assert pdf_path.is_file()

    pdf_bytes = pdf_path.read_bytes()

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) == (
        body["pdf_size_bytes"]
    )
    assert sha256(pdf_bytes).hexdigest() == (
        body["pdf_sha256"]
    )

    assert body["original_invoice_id"] == (
        original_invoice_id
    )
    assert body["cancellation_reason"] == (
        "Fehlerhafte Abrechnung"
    )

    original_response = client.get(
        f"/invoices/{original_invoice_id}"
    )

    assert original_response.status_code == 200

    original_body = original_response.json()

    assert original_body["status"] == "finalized"
    assert original_body["document_type"] == "invoice"
    assert original_body["cancelled_at"] is None

    reader = PdfReader(pdf_path)

    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    normalized_pdf_text = "".join(
        pdf_text.split()
    )

    assert "STORNORECHNUNG" in pdf_text
    assert "Stornodatum" in pdf_text
    assert "Stornonummer" in pdf_text
    assert "Stornobetrag" in pdf_text
    assert "Originalrechnung" in pdf_text
    assert "STORNORECHNUNG" in normalized_pdf_text
    assert "Fehlerhafte Abrechnung" in pdf_text
    assert "Hinweis" in pdf_text
    assert "Zahlungsbedingung" not in pdf_text

    original_invoice_number = (
        original_finalize_response.json()[
            "invoice_number"
        ]
    )

    assert original_invoice_number in pdf_text

    assert "Bitte bewahren Sie diesen Stornobeleg" in pdf_text
    assert "Elektronisch erstellter Stornobeleg" in pdf_text
    assert "Elektronisch erstellte Rechnung" not in pdf_text


def test_rebills_session_after_finalized_cancellation(
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

    original_draft_response = client.post(
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

    assert original_draft_response.status_code in {
        200,
        201,
    }

    original_draft = (
        original_draft_response.json()
    )
    original_invoice_id = original_draft["id"]
    original_item_id = (
        original_draft["items"][0]["id"]
    )

    original_finalize_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/finalize"
        ),
        json={
            "issue_date": "2026-07-05",
        },
    )

    assert (
        original_finalize_response.status_code
        == 200
    )

    cancellation_response = client.post(
        (
            f"/invoices/{original_invoice_id}"
            "/cancellations"
        ),
        json={
            "reason": "Fehlerhafte Abrechnung",
        },
    )

    assert cancellation_response.status_code == 201

    cancellation_id = (
        cancellation_response.json()["id"]
    )

    cancellation_finalize_response = client.post(
        (
            f"/invoices/{cancellation_id}"
            "/cancellation/finalize"
        ),
        json={
            "issue_date": "2026-07-06",
        },
    )

    assert (
        cancellation_finalize_response.status_code
        == 200
    )

    database_session.refresh(
        charging_session
    )

    assert charging_session.invoiced is False
    assert charging_session.invoice_id is None

    rebill_draft_response = client.post(
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

    assert rebill_draft_response.status_code in {
        200,
        201,
    }

    rebill_draft = rebill_draft_response.json()
    rebill_invoice_id = rebill_draft["id"]

    assert rebill_invoice_id != original_invoice_id
    assert len(rebill_draft["items"]) == 1

    rebill_item = rebill_draft["items"][0]

    assert rebill_item["id"] != original_item_id
    assert (
        rebill_item["charging_session_id"]
        == charging_session.id
    )
    assert (
        rebill_item["rebills_invoice_item_id"]
        == original_item_id
    )
    assert (
        rebill_item["reversed_invoice_item_id"]
        is None
    )

    rebill_finalize_response = client.post(
        (
            f"/invoices/{rebill_invoice_id}"
            "/finalize"
        ),
        json={
            "issue_date": "2026-07-07",
        },
    )

    assert (
        rebill_finalize_response.status_code
        == 200
    )

    database_session.refresh(
        charging_session
    )

    assert charging_session.invoiced is True
    assert (
        charging_session.invoice_id
        == rebill_invoice_id
    )

    original_response = client.get(
        f"/invoices/{original_invoice_id}"
    )
    cancellation_response = client.get(
        f"/invoices/{cancellation_id}"
    )

    assert original_response.status_code == 200
    assert cancellation_response.status_code == 200

    assert (
        original_response.json()["status"]
        == "finalized"
    )
    assert (
        cancellation_response.json()["status"]
        == "finalized"
    )

def test_deletes_invoice_draft(
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

    assert draft_response.status_code == 201

    invoice_id = draft_response.json()["id"]

    response = client.delete(
        f"/invoices/{invoice_id}"
    )

    assert response.status_code == 204
    assert response.content == b""

    assert database_session.get(
        Invoice,
        invoice_id,
    ) is None

    remaining_items = list(
        database_session.scalars(
            select(InvoiceItem).where(
                InvoiceItem.invoice_id
                == invoice_id
            )
        ).all()
    )

    assert remaining_items == []


def test_deleting_draft_releases_monthly_base_fee(
    client: TestClient,
    database_session: Session,
) -> None:
    user, _ = create_billable_session(
        database_session
    )

    database_session.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("10.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
        )
    )
    database_session.commit()

    draft = create_invoice_draft(
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

    assert len(draft.items) == 1

    original_invoice_id = draft.id
    charge_id = (
        draft.items[0]
        .monthly_base_fee_charge_id
    )

    assert charge_id is not None

    response = client.delete(
        f"/invoices/{original_invoice_id}"
    )

    assert response.status_code == 204

    assert database_session.get(
        Invoice,
        original_invoice_id,
    ) is None

    charge = database_session.get(
        MonthlyBaseFeeCharge,
        charge_id,
    )

    assert charge is not None
    assert charge.invoice_id is None
    assert charge.invoiced is False

    remaining_items = list(
        database_session.scalars(
            select(InvoiceItem).where(
                InvoiceItem.invoice_id
                == original_invoice_id
            )
        ).all()
    )

    assert remaining_items == []

    replacement_draft = create_invoice_draft(
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

    assert len(replacement_draft.items) == 1
    assert (
        replacement_draft.items[0]
        .monthly_base_fee_charge_id
        == charge_id
    )

    charge_ids = list(
        database_session.scalars(
            select(MonthlyBaseFeeCharge.id)
        ).all()
    )

    assert charge_ids == [charge_id]


def test_rejects_deleting_finalized_invoice(
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

    assert draft_response.status_code == 201

    invoice_id = draft_response.json()["id"]

    invoice = database_session.get(
        Invoice,
        invoice_id,
    )

    assert invoice is not None

    invoice.status = "finalized"
    database_session.commit()

    response = client.delete(
        f"/invoices/{invoice_id}"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Nur ein Entwurf kann gelöscht "
            "werden."
        ),
    }


def test_delete_invoice_returns_not_found(
    client: TestClient,
) -> None:
    response = client.delete(
        "/invoices/999999"
    )

    assert response.status_code == 404
