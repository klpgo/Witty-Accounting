from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.config import settings as app_settings
from app.database import Base
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.deleted_charging_session import (
    DeletedChargingSession,
)
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice, InvoiceItem
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.models.retention_purge import RetentionPurge
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.services.importers.import_filters import load_import_filters
from app.services.invoice_retention import (
    InvoiceRetentionError,
    RetentionPurgeBlockedError,
    build_overview,
    last_purgeable_year,
    purge_year,
)
from app.utils.utc import utc_now


TODAY = date(2027, 3, 1)  # 10 Jahre: bis einschließlich 2016 löschbar


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(GlobalSettings(id=1))
        db.commit()
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


def archive_root() -> Path:
    return Path(app_settings.invoice_pdf_archive_dir).resolve()


def make_user(
    db: Session,
    email: str = "customer@example.com",
    *,
    is_admin: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash="not-used",
        first_name="Erika",
        last_name="Muster",
        address="Musterweg 1",
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=True,
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def make_assignment(db: Session, user: User) -> RFIDCardAssignment:
    card = RFIDCard(rfid_number=f"CARD-{user.id}", active=True)
    db.add(card)
    db.flush()
    assignment = RFIDCardAssignment(
        rfid_card_id=card.id,
        user_id=user.id,
        valid_from=datetime(2010, 1, 1),
        valid_to=None,
    )
    db.add(assignment)
    db.flush()
    return assignment


def make_session(
    db: Session,
    assignment: RFIDCardAssignment,
    start: datetime,
    *,
    invoiced: bool = True,
    key: str = "a",
) -> ChargingSession:
    session = ChargingSession(
        hager_session_id=f"hager-{key}",
        station_id="WB2",
        start_time=start,
        end_time=start.replace(hour=start.hour + 1),
        rfid_card_id=assignment.rfid_card_id,
        rfid_assignment_id=assignment.id,
        energy_total_kwh=10.0,
        energy_pv_kwh=4.0,
        invoiced=invoiced,
        import_hash=key * 64,
        source="hager",
    )
    db.add(session)
    db.flush()
    return session


def make_fee(
    db: Session,
    assignment: RFIDCardAssignment,
    month: date,
) -> MonthlyBaseFeeCharge:
    fee = MonthlyBaseFeeCharge(
        rfid_card_id=assignment.rfid_card_id,
        rfid_assignment_id=assignment.id,
        user_id=assignment.user_id,
        fee_month=month,
        net_amount=Decimal("10.0000"),
        vat_rate=Decimal("19.00"),
        invoiced=True,
    )
    db.add(fee)
    db.flush()
    return fee


def make_invoice(
    db: Session,
    user: User,
    number: str,
    issue_date: date,
    *,
    document_type: str = "invoice",
    original: Invoice | None = None,
    status: str = "finalized",
) -> Invoice:
    invoice = Invoice(
        invoice_number=number if status == "finalized" else None,
        document_type=document_type,
        original_invoice_id=original.id if original else None,
        user_id=user.id,
        issuer_name="Witty Test",
        issuer_address="Testweg 1",
        recipient_name="Erika Muster",
        recipient_address="Musterweg 1",
        status=status,
        issue_date=issue_date if status == "finalized" else None,
        service_period_start=datetime(issue_date.year, 1, 1),
        service_period_end=datetime(issue_date.year, 2, 1),
        finalized_at=utc_now() if status == "finalized" else None,
    )

    if status == "finalized":
        relative = f"{issue_date.year}/{number}.pdf"
        path = archive_root() / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7 test")
        invoice.pdf_storage_path = relative
        invoice.pdf_sha256 = "0" * 64
        invoice.pdf_size_bytes = 13
        invoice.pdf_created_at = utc_now()

    db.add(invoice)
    db.flush()
    return invoice


def add_item(
    db: Session,
    invoice: Invoice,
    position: int,
    *,
    session: ChargingSession | None = None,
    fee: MonthlyBaseFeeCharge | None = None,
    reverses: InvoiceItem | None = None,
    rebills: InvoiceItem | None = None,
) -> InvoiceItem:
    item = InvoiceItem(
        invoice_id=invoice.id,
        item_type=(
            "monthly_base_fee" if fee is not None else "charging_session"
        ),
        charging_session_id=session.id if session else None,
        monthly_base_fee_charge_id=fee.id if fee else None,
        reversed_invoice_item_id=reverses.id if reverses else None,
        rebills_invoice_item_id=rebills.id if rebills else None,
        position_number=position,
        description="Position",
        net_amount=Decimal("1.0000"),
        vat_rate=Decimal("19.00"),
        vat_amount=Decimal("0.19"),
        gross_amount=Decimal("1.19"),
    )
    db.add(item)
    db.flush()

    if session is not None:
        session.invoice_id = invoice.id
    if fee is not None:
        fee.invoice_id = invoice.id

    return item


def billed_invoice(
    db: Session,
    user: User,
    assignment: RFIDCardAssignment,
    number: str,
    issue_date: date,
    key: str,
) -> Invoice:
    invoice = make_invoice(db, user, number, issue_date)
    session = make_session(
        db,
        assignment,
        datetime(issue_date.year, 1, 10, 10),
        key=key,
    )
    fee = make_fee(db, assignment, date(issue_date.year, 1, 1))
    add_item(db, invoice, 1, session=session)
    add_item(db, invoice, 2, fee=fee)
    return invoice


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def three_years(database_session: Session) -> dict[str, Any]:
    db = database_session
    user = make_user(db)
    assignment = make_assignment(db, user)
    invoices = {
        2015: billed_invoice(db, user, assignment, "RE-2015-0001", date(2015, 2, 1), "a"),
        2016: billed_invoice(db, user, assignment, "RE-2016-0001", date(2016, 2, 1), "b"),
        2017: billed_invoice(db, user, assignment, "RE-2017-0001", date(2017, 2, 1), "c"),
    }
    db.commit()
    return {"user": user, "assignment": assignment, "invoices": invoices}


# --------------------------------------------------------------------------
# Frist
# --------------------------------------------------------------------------


def test_retention_period_starts_at_end_of_issue_year() -> None:
    assert last_purgeable_year(10, date(2037, 1, 1)) == 2026
    assert last_purgeable_year(10, date(2036, 12, 31)) == 2025
    assert last_purgeable_year(8, date(2035, 1, 1)) == 2026


def test_default_retention_is_ten_years(database_session: Session) -> None:
    settings = database_session.get(GlobalSettings, 1)
    assert settings.invoice_retention_years == 10


# --------------------------------------------------------------------------
# Übersicht
# --------------------------------------------------------------------------


def test_overview_lists_expired_years_oldest_first(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    overview = build_overview(database_session, today=TODAY)

    assert overview["last_purgeable_year"] == 2016
    assert [y["year"] for y in overview["years"]] == [2015, 2016]

    first, second = overview["years"]
    assert first["purgeable"] is True
    assert first["invoices"] == 1
    assert first["pdf_files"] == 1
    assert first["first_invoice_number"] == "RE-2015-0001"
    assert second["purgeable"] is False
    assert [b["code"] for b in second["blockers"]] == ["older_year_pending"]


def test_cancellation_moves_group_to_later_year(
    database_session: Session,
) -> None:
    db = database_session
    user = make_user(db)
    original = make_invoice(db, user, "RE-2016-0007", date(2016, 12, 20))
    make_invoice(
        db,
        user,
        "ST-2017-0001",
        date(2017, 1, 5),
        document_type="cancellation",
        original=original,
    )
    db.commit()

    overview = build_overview(db, today=TODAY)

    assert overview["years"] == []

    overview = build_overview(db, today=date(2028, 1, 1))
    assert overview["years"][0]["year"] == 2017
    assert overview["years"][0]["cancellations"] == 1
    assert overview["years"][0]["pdf_files"] == 2


def test_unbilled_and_draft_data_block_the_year(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    db = database_session
    assignment = three_years["assignment"]
    make_session(
        db,
        assignment,
        datetime(2015, 6, 1, 10),
        invoiced=False,
        key="open",
    )
    make_invoice(
        db,
        three_years["user"],
        "-",
        date(2015, 3, 1),
        status="draft",
    )
    db.commit()

    year = build_overview(db, today=TODAY)["years"][0]

    assert {b["code"] for b in year["blockers"]} == {
        "unbilled_charging_sessions",
        "draft_invoices",
    }

    with pytest.raises(RetentionPurgeBlockedError):
        purge_year(db, year=2015, confirm_year=2015, today=TODAY)


# --------------------------------------------------------------------------
# Löschen
# --------------------------------------------------------------------------


def test_purge_deletes_year_and_keeps_newer_data(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    db = database_session
    user_id = three_years["user"].id
    pdf_2015 = archive_root() / "2015" / "RE-2015-0001.pdf"
    pdf_2016 = archive_root() / "2016" / "RE-2016-0001.pdf"
    assert pdf_2015.exists()

    result = purge_year(
        db,
        year=2015,
        confirm_year=2015,
        purged_by="Admin <admin@example.com>",
        today=TODAY,
    )

    assert result.invoices == 1
    assert result.charging_sessions == 1
    assert result.base_fees == 1
    assert result.pdf_files == 1
    assert result.pdf_errors == []

    numbers = db.scalars(select(Invoice.invoice_number)).all()
    assert sorted(numbers) == ["RE-2016-0001", "RE-2017-0001"]
    assert count(db, InvoiceItem) == 4
    assert count(db, ChargingSession) == 2
    assert count(db, MonthlyBaseFeeCharge) == 2

    assert not pdf_2015.exists()
    assert not pdf_2015.parent.exists()
    assert pdf_2016.exists()

    # Kunde und Kartenzuordnung bleiben
    assert db.get(User, user_id) is not None
    assert count(db, RFIDCardAssignment) == 1

    protocol = db.scalar(select(RetentionPurge))
    assert protocol.year == 2015
    assert protocol.retention_years == 10
    assert protocol.first_invoice_number == "RE-2015-0001"
    assert protocol.pdf_files == 1
    assert protocol.purged_by == "Admin <admin@example.com>"

    assert db.get(GlobalSettings, 1).retention_purged_through_year == 2015

    # 2016 ist jetzt das älteste Jahr und löschbar
    overview = build_overview(db, today=TODAY)
    assert [y["year"] for y in overview["years"]] == [2016]
    assert overview["years"][0]["purgeable"] is True
    assert overview["protocol"][0]["year"] == 2015


def test_purge_requires_matching_confirmation_and_expired_year(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    db = database_session

    with pytest.raises(InvoiceRetentionError):
        purge_year(db, year=2015, confirm_year=2016, today=TODAY)

    with pytest.raises(RetentionPurgeBlockedError):
        purge_year(db, year=2017, confirm_year=2017, today=TODAY)

    with pytest.raises(RetentionPurgeBlockedError):
        purge_year(db, year=2016, confirm_year=2016, today=TODAY)

    assert count(db, Invoice) == 3


def test_purge_keeps_rebilled_sessions_of_newer_invoices(
    database_session: Session,
) -> None:
    db = database_session
    user = make_user(db)
    assignment = make_assignment(db, user)
    session = make_session(db, assignment, datetime(2015, 11, 3, 9), key="r")

    original = make_invoice(db, user, "RE-2015-0001", date(2015, 12, 1))
    original_item = add_item(db, original, 1, session=session)
    cancellation = make_invoice(
        db,
        user,
        "ST-2015-0001",
        date(2015, 12, 15),
        document_type="cancellation",
        original=original,
    )
    add_item(db, cancellation, 1, reverses=original_item)

    corrected = make_invoice(db, user, "RE-2016-0001", date(2016, 1, 10))
    rebill_item = add_item(
        db, corrected, 1, session=session, rebills=original_item
    )
    db.commit()

    result = purge_year(db, year=2015, confirm_year=2015, today=TODAY)

    assert result.invoices == 1
    assert result.cancellations == 1
    assert result.pdf_files == 2
    assert result.charging_sessions == 0

    db.refresh(rebill_item)
    assert rebill_item.rebills_invoice_item_id is None
    assert rebill_item.charging_session_id == session.id
    assert db.get(ChargingSession, session.id) is not None
    assert db.get(Invoice, corrected.id) is not None


def test_purge_removes_discarded_sessions_and_markers_of_the_period(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    db = database_session
    assignment = three_years["assignment"]
    discarded = make_session(
        db, assignment, datetime(2015, 4, 1, 10), invoiced=False, key="d"
    )
    discarded.discarded_at = utc_now()
    newer_discarded = make_session(
        db, assignment, datetime(2016, 4, 1, 10), invoiced=False, key="e"
    )
    newer_discarded.discarded_at = utc_now()
    db.add_all(
        [
            DeletedChargingSession(
                import_hash="x" * 64, start_time=datetime(2015, 5, 1)
            ),
            DeletedChargingSession(
                import_hash="y" * 64, start_time=datetime(2016, 5, 1)
            ),
        ]
    )
    db.commit()

    result = purge_year(db, year=2015, confirm_year=2015, today=TODAY)

    assert result.charging_sessions == 2
    remaining = db.scalars(select(ChargingSession.import_hash)).all()
    assert "d" * 64 not in remaining
    assert "e" * 64 in remaining
    markers = db.scalars(select(DeletedChargingSession.import_hash)).all()
    assert markers == ["y" * 64]


def test_purged_years_are_not_imported_again(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    db = database_session
    settings = db.get(GlobalSettings, 1)
    settings.billing_start_date = date(2014, 1, 1)
    db.commit()

    assert load_import_filters(db).not_before == date(2014, 1, 1)

    purge_year(db, year=2015, confirm_year=2015, today=TODAY)

    assert load_import_filters(db).not_before == date(2016, 1, 1)


def test_missing_pdf_file_is_tolerated(
    database_session: Session,
    three_years: dict[str, Any],
) -> None:
    (archive_root() / "2015" / "RE-2015-0001.pdf").unlink()

    result = purge_year(
        database_session, year=2015, confirm_year=2015, today=TODAY
    )

    assert result.pdf_errors == []
    assert count(database_session, Invoice) == 2


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_api_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = make_user(database_session)
    database_session.commit()

    assert client.get("/api/retention", headers=header(user)).status_code == 403
    assert client.get("/api/retention/due", headers=header(user)).status_code == 403
    response = client.post(
        "/api/retention/years/2010/purge",
        json={"confirm_year": 2010},
        headers=header(user),
    )
    assert response.status_code == 403


def test_api_settings_and_purge(
    client: TestClient,
    database_session: Session,
) -> None:
    db = database_session
    admin = make_user(db, "admin@example.com", is_admin=True)
    assignment = make_assignment(db, admin)
    billed_invoice(db, admin, assignment, "RE-2010-0001", date(2010, 2, 1), "a")
    db.commit()

    response = client.patch(
        "/api/retention/settings",
        json={"retention_years": 5},
        headers=header(admin),
    )
    assert response.status_code == 422

    response = client.patch(
        "/api/retention/settings",
        json={"retention_years": 10},
        headers=header(admin),
    )
    assert response.status_code == 200
    assert response.json()["retention_years"] == 10

    response = client.get("/api/retention", headers=header(admin))
    assert response.status_code == 200
    assert response.json()["years"][0]["year"] == 2010

    response = client.get("/api/retention/due", headers=header(admin))
    assert response.json() == {"year": 2010}

    response = client.post(
        "/api/retention/years/2010/purge",
        json={"confirm_year": 2011},
        headers=header(admin),
    )
    assert response.status_code == 422

    response = client.post(
        "/api/retention/years/2010/purge",
        json={"confirm_year": 2010},
        headers=header(admin),
    )
    assert response.status_code == 200
    assert response.json()["invoices"] == 1

    response = client.get("/api/retention", headers=header(admin))
    body = response.json()
    assert body["years"] == []
    assert body["purged_through_year"] == 2010
    assert body["protocol"][0]["purged_by"] == (
        "Erika Muster <admin@example.com>"
    )

    response = client.get("/api/retention/due", headers=header(admin))
    assert response.json() == {"year": None}
