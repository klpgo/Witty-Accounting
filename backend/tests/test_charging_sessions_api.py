from collections.abc import Generator
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.invoice import Invoice
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User


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

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = (
        override_get_db
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_user(
    db: Session,
    *,
    email: str,
    first_name: str,
    is_admin: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash="not-used",
        first_name=first_name,
        last_name="Test",
        address="Teststraße 1, 12345 Teststadt",
        phone=None,
        invoice_delivery_email=False,
        invoice_delivery_post=False,
        active=True,
        is_admin=is_admin,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_card_assignment(
    db: Session,
    *,
    user: User,
    suffix: str,
) -> tuple[RFIDCard, RFIDCardAssignment]:
    card = RFIDCard(
        rfid_number=f"TEST-CARD-{suffix}",
        description=f"Testkarte {suffix}",
        active=True,
    )

    assignment = RFIDCardAssignment(
        rfid_card=card,
        user=user,
        valid_from=datetime(2026, 1, 1),
        valid_to=None,
    )

    db.add_all([card, assignment])
    db.commit()
    db.refresh(card)
    db.refresh(assignment)

    return card, assignment


def create_invoice(
    db: Session,
    *,
    user: User,
    status: str,
    invoice_number: str | None,
) -> Invoice:
    invoice = Invoice(
        invoice_number=invoice_number,
        document_type="invoice",
        user_id=user.id,
        issuer_name="Witty Accounting",
        issuer_address="Testweg 1, 12345 Teststadt",
        issuer_tax_number=None,
        issuer_vat_id=None,
        issuer_bank_name=None,
        issuer_iban=None,
        issuer_bic=None,
        recipient_name=(
            f"{user.first_name} {user.last_name}"
        ),
        recipient_address=user.address or "Testadresse",
        status=status,
        issue_date=None,
        due_date=None,
        service_period_start=datetime(2026, 6, 1),
        service_period_end=datetime(2026, 7, 1),
        currency="EUR",
        total_net=Decimal("10.00"),
        vat_amount=Decimal("1.90"),
        total_gross=Decimal("11.90"),
        finalized_at=(
            datetime(2026, 7, 5, 12, 0)
            if status == "finalized"
            else None
        ),
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return invoice


def create_charging_session(
    db: Session,
    *,
    suffix: str,
    start_time: datetime,
    card: RFIDCard | None = None,
    assignment: RFIDCardAssignment | None = None,
    invoice: Invoice | None = None,
    invoiced: bool = False,
) -> ChargingSession:
    session = ChargingSession(
        hager_session_id=None,
        station_id=f"WB-{suffix}",
        import_hash=f"{suffix:0<64}"[:64],
        source="xlsx",
        start_time=start_time,
        end_time=start_time.replace(
            hour=start_time.hour + 1
        ),
        rfid_card=card,
        rfid_assignment=assignment,
        energy_total_kwh=10.0,
        energy_pv_kwh=4.0,
        cost_grid_net=Decimal("1.8000"),
        cost_pv_net=Decimal("0.4000"),
        vat_rate=Decimal("19.00"),
        invoiced=invoiced,
        invoice_id=(
            invoice.id
            if invoice is not None
            else None
        ),
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def authorization_header(
    user: User,
) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {create_access_token(user)}"
        )
    }


def test_rejects_unauthenticated_access(
    client: TestClient,
) -> None:
    response = client.get("/api/charging-sessions")

    assert response.status_code == 401


def test_admin_reads_all_charging_sessions(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    own_user = create_user(
        database_session,
        email="own@example.com",
        first_name="Own",
    )
    foreign_user = create_user(
        database_session,
        email="foreign@example.com",
        first_name="Foreign",
    )

    own_card, own_assignment = create_card_assignment(
        database_session,
        user=own_user,
        suffix="OWN",
    )
    foreign_card, foreign_assignment = (
        create_card_assignment(
            database_session,
            user=foreign_user,
            suffix="FOREIGN",
        )
    )

    finalized_invoice = create_invoice(
        database_session,
        user=own_user,
        status="finalized",
        invoice_number="RE-2026-0001",
    )
    draft_invoice = create_invoice(
        database_session,
        user=own_user,
        status="draft",
        invoice_number=None,
    )

    oldest = create_charging_session(
        database_session,
        suffix="UNASSIGNED",
        start_time=datetime(2026, 6, 1, 8, 0),
    )
    foreign = create_charging_session(
        database_session,
        suffix="FOREIGN",
        start_time=datetime(2026, 6, 2, 8, 0),
        card=foreign_card,
        assignment=foreign_assignment,
    )
    draft = create_charging_session(
        database_session,
        suffix="DRAFT",
        start_time=datetime(2026, 6, 3, 8, 0),
        card=own_card,
        assignment=own_assignment,
        invoice=draft_invoice,
        invoiced=True,
    )
    finalized = create_charging_session(
        database_session,
        suffix="FINAL",
        start_time=datetime(2026, 6, 4, 8, 0),
        card=own_card,
        assignment=own_assignment,
        invoice=finalized_invoice,
        invoiced=True,
    )

    response = client.get(
        "/api/charging-sessions",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200

    data = response.json()

    assert [
        item["id"]
        for item in data
    ] == [
        finalized.id,
        draft.id,
        foreign.id,
        oldest.id,
    ]

    assert data[0]["user_id"] == own_user.id
    assert data[0]["rfid_number"] == (
        own_card.rfid_number
    )
    assert data[0]["invoiced"] is True
    assert (
        data[0]["invoice_id"]
        == finalized_invoice.id
    )
    assert (
        data[0]["invoice_number"]
        == "RE-2026-0001"
    )
    assert data[0]["invoice_status"] == "finalized"

    assert data[1]["invoiced"] is True
    assert data[1]["invoice_id"] == draft_invoice.id
    assert data[1]["invoice_status"] == "draft"

    assert data[3]["user_id"] is None
    assert data[3]["rfid_number"] is None


def test_user_reads_only_own_charging_sessions(
    client: TestClient,
    database_session: Session,
) -> None:
    own_user = create_user(
        database_session,
        email="own@example.com",
        first_name="Own",
    )
    foreign_user = create_user(
        database_session,
        email="foreign@example.com",
        first_name="Foreign",
    )

    own_card, own_assignment = create_card_assignment(
        database_session,
        user=own_user,
        suffix="OWN",
    )
    foreign_card, foreign_assignment = (
        create_card_assignment(
            database_session,
            user=foreign_user,
            suffix="FOREIGN",
        )
    )

    finalized_invoice = create_invoice(
        database_session,
        user=own_user,
        status="finalized",
        invoice_number="RE-2026-0001",
    )
    draft_invoice = create_invoice(
        database_session,
        user=own_user,
        status="draft",
        invoice_number=None,
    )

    open_session = create_charging_session(
        database_session,
        suffix="OPEN",
        start_time=datetime(2026, 6, 1, 8, 0),
        card=own_card,
        assignment=own_assignment,
    )
    draft_session = create_charging_session(
        database_session,
        suffix="DRAFT",
        start_time=datetime(2026, 6, 2, 8, 0),
        card=own_card,
        assignment=own_assignment,
        invoice=draft_invoice,
        invoiced=True,
    )
    finalized_session = create_charging_session(
        database_session,
        suffix="FINAL",
        start_time=datetime(2026, 6, 3, 8, 0),
        card=own_card,
        assignment=own_assignment,
        invoice=finalized_invoice,
        invoiced=True,
    )

    create_charging_session(
        database_session,
        suffix="FOREIGN",
        start_time=datetime(2026, 6, 4, 8, 0),
        card=foreign_card,
        assignment=foreign_assignment,
    )
    create_charging_session(
        database_session,
        suffix="UNASSIGNED",
        start_time=datetime(2026, 6, 5, 8, 0),
    )

    response = client.get(
        "/api/charging-sessions",
        headers=authorization_header(own_user),
    )

    assert response.status_code == 200

    data = response.json()

    assert [
        item["id"]
        for item in data
    ] == [
        finalized_session.id,
        draft_session.id,
        open_session.id,
    ]

    assert data[0]["invoiced"] is True
    assert data[0]["rfid_number"] == (
        own_card.rfid_number
    )
    assert (
        data[0]["invoice_id"]
        == finalized_invoice.id
    )
    assert (
        data[0]["invoice_number"]
        == "RE-2026-0001"
    )
    assert data[0]["invoice_status"] == "finalized"

    assert data[1]["invoiced"] is False
    assert data[1]["invoice_id"] is None
    assert data[1]["invoice_number"] is None
    assert data[1]["invoice_status"] is None

    assert data[2]["invoiced"] is False
    assert data[2]["invoice_id"] is None
