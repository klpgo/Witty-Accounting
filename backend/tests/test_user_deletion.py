from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.deleted_charging_session import (
    DeletedChargingSession,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.models.password_reset_token import (
    PasswordResetToken,
)
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.services.deleted_sessions import find_deleted_session
from app.services.importers.hager_json_importer import (
    import_charging_rows_to_db,
)
from app.services.invoice_cancellation import (
    InvoiceCancellationStateError,
    create_cancellation_draft,
)
from app.services.user_deletion import (
    UserDeletionBlockedError,
    check_user_deletion,
    delete_user,
)
from app.utils.utc import utc_now


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
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
    def override_get_db() -> Generator[Session, None, None]:
        yield database_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def make_user(
    db: Session,
    *,
    email: str,
    is_admin: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash="not-used",
        first_name="Erika",
        last_name="Muster",
        address="Musterweg 1, 12345 Musterstadt",
        phone=None,
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def make_card_assignment(
    db: Session,
    user: User,
    *,
    rfid_number: str = "CARD-1",
    valid_to: datetime | None = datetime(2026, 7, 1),
) -> tuple[RFIDCard, RFIDCardAssignment]:
    card = RFIDCard(rfid_number=rfid_number, active=True)
    db.add(card)
    db.flush()

    assignment = RFIDCardAssignment(
        rfid_card_id=card.id,
        user_id=user.id,
        valid_from=datetime(2026, 1, 1),
        valid_to=valid_to,
    )
    db.add(assignment)
    db.flush()
    return card, assignment


def make_session(
    db: Session,
    card: RFIDCard,
    assignment: RFIDCardAssignment,
    *,
    invoiced: bool,
    hash_char: str = "a",
    start: datetime = datetime(2026, 6, 17, 10, 0),
) -> ChargingSession:
    session = ChargingSession(
        hager_session_id=f"hager-{hash_char}",
        station_id="WB2",
        wallbox_id="WB-A",
        start_time=start,
        end_time=start.replace(hour=start.hour + 1),
        rfid_number=card.rfid_number,
        rfid_card_id=card.id,
        rfid_assignment_id=assignment.id,
        energy_total_kwh=10.0,
        energy_pv_kwh=4.0,
        cost_grid_net=Decimal("1.8000"),
        cost_pv_net=Decimal("0.4000"),
        vat_rate=Decimal("19.00"),
        invoiced=invoiced,
        invoice_id=None,
        import_hash=hash_char * 64,
        source="hager",
    )
    db.add(session)
    db.flush()
    return session


def make_invoice(
    db: Session,
    user: User,
    *,
    status: str = "finalized",
    with_pdf: bool = True,
    number: str = "RE-2026-0001",
) -> Invoice:
    invoice = Invoice(
        invoice_number=number if status == "finalized" else None,
        document_type="invoice",
        user_id=user.id,
        issuer_name="Witty Test",
        issuer_address="Testweg 1, 12345 Teststadt",
        recipient_name="Erika Muster",
        recipient_address="Musterweg 1, 12345 Musterstadt",
        status=status,
        issue_date=date(2026, 7, 2) if status == "finalized" else None,
        service_period_start=datetime(2026, 6, 1),
        service_period_end=datetime(2026, 7, 1),
        total_net=Decimal("12.20"),
        vat_amount=Decimal("2.32"),
        total_gross=Decimal("14.52"),
        finalized_at=utc_now() if status == "finalized" else None,
    )

    if with_pdf and status == "finalized":
        invoice.pdf_storage_path = f"2026/{number}.pdf"
        invoice.pdf_sha256 = "0" * 64
        invoice.pdf_size_bytes = 1234
        invoice.pdf_created_at = utc_now()

    db.add(invoice)
    db.flush()
    return invoice


def billed_customer(db: Session) -> dict[str, Any]:
    """Kunde mit beendeter Kartenzuordnung und vollständig abgerechneten,
    archivierten Daten."""
    admin = make_user(db, email="admin@example.com", is_admin=True)
    customer = make_user(db, email="customer@example.com")
    card, assignment = make_card_assignment(db, customer)
    session = make_session(db, card, assignment, invoiced=True)
    invoice = make_invoice(db, customer)
    session.invoice_id = invoice.id

    fee = MonthlyBaseFeeCharge(
        rfid_card_id=card.id,
        rfid_assignment_id=assignment.id,
        user_id=customer.id,
        fee_month=date(2026, 6, 1),
        net_amount=Decimal("10.0000"),
        vat_rate=Decimal("19.00"),
        invoiced=True,
        invoice_id=invoice.id,
    )
    db.add(fee)
    db.flush()

    db.add_all(
        [
            InvoiceItem(
                invoice_id=invoice.id,
                item_type="charging_session",
                charging_session_id=session.id,
                position_number=1,
                description="Ladevorgang WB2",
                session_start=session.start_time,
                session_end=session.end_time,
                station_id="WB2",
                energy_total_kwh=Decimal("10.0000"),
                net_amount=Decimal("2.2000"),
                vat_rate=Decimal("19.00"),
                vat_amount=Decimal("0.42"),
                gross_amount=Decimal("2.62"),
            ),
            InvoiceItem(
                invoice_id=invoice.id,
                item_type="monthly_base_fee",
                monthly_base_fee_charge_id=fee.id,
                position_number=2,
                description="Grundgebühr Juni 2026",
                net_amount=Decimal("10.0000"),
                vat_rate=Decimal("19.00"),
                vat_amount=Decimal("1.90"),
                gross_amount=Decimal("11.90"),
            ),
            PasswordResetToken(
                user_id=customer.id,
                token_hash="t" * 64,
                expires_at=datetime(2030, 1, 1),
            ),
        ]
    )
    db.commit()

    return {
        "admin": admin,
        "customer": customer,
        "card": card,
        "assignment": assignment,
        "session": session,
        "invoice": invoice,
        "fee": fee,
    }


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------
# Prüfung
# --------------------------------------------------------------------------


def test_check_allows_fully_billed_customer(
    database_session: Session,
) -> None:
    data = billed_customer(database_session)

    check = check_user_deletion(
        database_session,
        user_id=data["customer"].id,
        acting_user_id=data["admin"].id,
    ).as_dict()

    assert check["can_delete"] is True
    assert check["blockers"] == []
    assert check["charging_sessions"] == 1
    assert check["base_fees"] == 1
    assert check["rfid_assignments"] == 1
    assert check["invoices_kept"] == 1


def test_own_account_is_blocked(database_session: Session) -> None:
    admin = make_user(database_session, email="admin@example.com", is_admin=True)
    database_session.commit()

    check = check_user_deletion(
        database_session,
        user_id=admin.id,
        acting_user_id=admin.id,
    )

    assert [b.code for b in check.blockers] == ["own_account"]


def test_draft_active_assignment_and_missing_pdf_block_deletion(
    database_session: Session,
) -> None:
    customer = make_user(database_session, email="customer@example.com")
    make_card_assignment(database_session, customer, valid_to=None)
    make_invoice(database_session, customer, status="draft")
    make_invoice(
        database_session,
        customer,
        with_pdf=False,
        number="RE-2026-0002",
    )
    database_session.commit()

    check = check_user_deletion(database_session, user_id=customer.id)
    codes = {b.code for b in check.blockers}

    assert codes == {
        "draft_invoices",
        "missing_invoice_pdfs",
        "active_rfid_assignments",
    }
    assert check.as_dict()["can_delete_with_discard"] is False

    with pytest.raises(UserDeletionBlockedError):
        delete_user(
            database_session,
            user_id=customer.id,
            discard_unbilled=True,
        )

    assert database_session.get(User, customer.id) is not None


def test_unbilled_data_blocks_unless_discarded(
    database_session: Session,
) -> None:
    customer = make_user(database_session, email="customer@example.com")
    card, assignment = make_card_assignment(database_session, customer)
    make_session(database_session, card, assignment, invoiced=False)
    database_session.add(
        MonthlyBaseFeeCharge(
            rfid_card_id=card.id,
            rfid_assignment_id=assignment.id,
            user_id=customer.id,
            fee_month=date(2026, 6, 1),
            net_amount=Decimal("10.0000"),
            vat_rate=Decimal("19.00"),
            invoiced=False,
        )
    )
    database_session.commit()

    check = check_user_deletion(database_session, user_id=customer.id)

    assert {b.code for b in check.blockers} == {
        "unbilled_charging_sessions",
        "unbilled_base_fees",
    }
    assert all(b.discardable for b in check.blockers)
    assert check.as_dict()["can_delete"] is False
    assert check.as_dict()["can_delete_with_discard"] is True

    with pytest.raises(UserDeletionBlockedError):
        delete_user(database_session, user_id=customer.id)

    # ID vorher merken: nach dem Löschen ist das Objekt nicht mehr ladbar
    customer_id = customer.id

    result = delete_user(
        database_session,
        user_id=customer_id,
        discard_unbilled=True,
    )

    assert result.charging_sessions == 1
    assert result.base_fees == 1
    assert database_session.get(User, customer_id) is None
    assert count(database_session, ChargingSession) == 0
    assert count(database_session, MonthlyBaseFeeCharge) == 0


def test_discarded_sessions_do_not_block(
    database_session: Session,
) -> None:
    customer = make_user(database_session, email="customer@example.com")
    card, assignment = make_card_assignment(database_session, customer)
    session = make_session(database_session, card, assignment, invoiced=False)
    session.discarded_at = utc_now()
    database_session.commit()

    check = check_user_deletion(database_session, user_id=customer.id)

    assert check.blockers == []


# --------------------------------------------------------------------------
# Löschen
# --------------------------------------------------------------------------


def test_delete_removes_billing_data_and_keeps_invoices(
    database_session: Session,
) -> None:
    data = billed_customer(database_session)
    customer_id = data["customer"].id
    invoice_id = data["invoice"].id
    card_id = data["card"].id

    result = delete_user(
        database_session,
        user_id=customer_id,
        acting_user_id=data["admin"].id,
    )

    assert result.charging_sessions == 1
    assert result.base_fees == 1
    assert result.rfid_assignments == 1
    assert result.invoices_kept == 1

    db = database_session
    assert db.get(User, customer_id) is None
    assert count(db, ChargingSession) == 0
    assert count(db, MonthlyBaseFeeCharge) == 0
    assert count(db, RFIDCardAssignment) == 0
    assert count(db, PasswordResetToken) == 0

    # Karte gehört dem Betreiber und bleibt
    assert db.get(RFIDCard, card_id) is not None

    invoice = db.get(Invoice, invoice_id)
    assert invoice is not None
    assert invoice.user_id is None
    assert invoice.recipient_name == "Erika Muster"
    assert invoice.recipient_address == "Musterweg 1, 12345 Musterstadt"
    assert invoice.pdf_storage_path == "2026/RE-2026-0001.pdf"
    assert invoice.total_gross == Decimal("14.52")

    items = db.scalars(
        select(InvoiceItem).order_by(InvoiceItem.position_number)
    ).all()
    assert len(items) == 2
    assert items[0].charging_session_id is None
    assert items[0].station_id == "WB2"
    assert items[0].energy_total_kwh == Decimal("10.0000")
    assert items[1].monthly_base_fee_charge_id is None
    assert items[1].description == "Grundgebühr Juni 2026"

    tombstone = db.scalar(select(DeletedChargingSession))
    assert tombstone is not None
    assert tombstone.hager_session_id == "hager-a"
    assert tombstone.import_hash == "a" * 64
    assert tombstone.wallbox_id == "WB-A"


def test_delete_keeps_other_users_data(
    database_session: Session,
) -> None:
    data = billed_customer(database_session)
    other = make_user(database_session, email="other@example.com")
    card, assignment = make_card_assignment(
        database_session, other, rfid_number="CARD-2"
    )
    make_session(
        database_session, card, assignment, invoiced=False, hash_char="b"
    )
    make_invoice(database_session, other, number="RE-2026-0009")
    database_session.commit()

    delete_user(database_session, user_id=data["customer"].id)

    assert database_session.get(User, other.id) is not None
    assert count(database_session, ChargingSession) == 1
    assert count(database_session, RFIDCardAssignment) == 1
    other_invoice = database_session.scalar(
        select(Invoice).where(Invoice.invoice_number == "RE-2026-0009")
    )
    assert other_invoice.user_id == other.id


def test_deleted_sessions_are_not_imported_again(
    database_session: Session,
) -> None:
    db = database_session
    customer = make_user(db, email="customer@example.com")
    make_card_assignment(
        db,
        customer,
        rfid_number="A1B2C3D4",
        valid_to=datetime(2026, 9, 1),
    )
    db.commit()

    row = {
        "sessionID": "WB-A-1786536541000-12ab3c4d",
        "wallboxID": "WB-A",
        "startAt": "2026-08-12T12:09:01.000Z",
        "stopAt": "2026-08-12T12:14:03.000Z",
        "authType": "RFID",
        "authData": "a1b2c3d4",
        "energyAll": "188.00",
        "energySolar": "180.00",
        "status": "FINISHED",
    }
    names = {"WB-A": "WB2"}

    first = import_charging_rows_to_db(db, [row], names)
    assert first["imported"] == 1
    assert db.scalar(select(ChargingSession)).rfid_assignment_id is not None

    delete_user(db, user_id=customer.id, discard_unbilled=True)
    assert count(db, ChargingSession) == 0

    # gleiche Session-ID
    again = import_charging_rows_to_db(db, [row], names)
    assert again["imported"] == 0
    assert again["skipped"] == 1

    # andere Session-ID, aber gleiche Wallbox und Startzeit
    renamed = dict(row, sessionID="other-id")
    again = import_charging_rows_to_db(db, [renamed], {"WB-A": "Garage"})
    assert again["imported"] == 0
    assert count(db, ChargingSession) == 0


def test_find_deleted_session_by_hash(database_session: Session) -> None:
    database_session.add(
        DeletedChargingSession(
            hager_session_id=None,
            import_hash="h" * 64,
            start_time=datetime(2026, 5, 1, 8, 0),
            wallbox_id=None,
            station_id="WB2",
        )
    )
    database_session.commit()

    assert find_deleted_session(
        database_session,
        start_time=datetime(2026, 5, 1, 8, 0),
        import_hash="h" * 64,
    ) is not None
    assert find_deleted_session(
        database_session,
        start_time=datetime(2026, 5, 1, 8, 0),
        import_hash="x" * 64,
    ) is None
    assert find_deleted_session(
        database_session,
        start_time=datetime(2026, 5, 1, 8, 0),
        station_aliases={"WB2"},
    ) is not None


def test_invoice_of_deleted_user_cannot_be_cancelled(
    database_session: Session,
) -> None:
    data = billed_customer(database_session)
    invoice_id = data["invoice"].id

    delete_user(database_session, user_id=data["customer"].id)

    with pytest.raises(InvoiceCancellationStateError):
        create_cancellation_draft(
            database_session,
            original_invoice_id=invoice_id,
            reason="Test",
        )


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def test_api_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    data = billed_customer(database_session)
    customer = data["customer"]

    response = client.delete(
        f"/api/users/{customer.id}",
        headers=header(customer),
    )
    assert response.status_code == 403

    response = client.get(
        f"/api/users/{customer.id}/deletion-check",
        headers=header(customer),
    )
    assert response.status_code == 403


def test_api_check_and_delete(
    client: TestClient,
    database_session: Session,
) -> None:
    data = billed_customer(database_session)
    admin = data["admin"]
    customer_id = data["customer"].id
    invoice_id = data["invoice"].id

    response = client.get(
        f"/api/users/{customer_id}/deletion-check",
        headers=header(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["can_delete"] is True
    assert body["invoices_kept"] == 1

    response = client.delete(
        f"/api/users/{customer_id}",
        headers=header(admin),
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/users/{customer_id}",
        headers=header(admin),
    )
    assert response.status_code == 404

    response = client.get(
        f"/api/invoices/{invoice_id}",
        headers=header(admin),
    )
    assert response.status_code == 200
    assert response.json()["user_id"] is None
    assert response.json()["recipient_name"] == "Erika Muster"


def test_api_reports_blockers(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = make_user(database_session, email="admin@example.com", is_admin=True)
    customer = make_user(database_session, email="customer@example.com")
    card, assignment = make_card_assignment(database_session, customer)
    make_session(database_session, card, assignment, invoiced=False)
    database_session.commit()

    response = client.delete(
        f"/api/users/{customer.id}",
        headers=header(admin),
    )
    assert response.status_code == 409
    assert "not been billed" in response.json()["detail"]

    response = client.delete(
        f"/api/users/{customer.id}?discard_unbilled=true",
        headers=header(admin),
    )
    assert response.status_code == 204


def test_api_rejects_own_account(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = make_user(database_session, email="admin@example.com", is_admin=True)
    database_session.commit()

    response = client.delete(
        f"/api/users/{admin.id}",
        headers=header(admin),
    )
    assert response.status_code == 409

    response = client.delete(
        "/api/users/9999",
        headers=header(admin),
    )
    assert response.status_code == 404
