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
from app.models.charging_session import ChargingSession
from app.models.invoice import Invoice, InvoiceItem
from app.models.wallbox import Wallbox
from app.services.wallboxes import (
    apply_name_to_open_sessions,
    display_name,
    display_names,
    ensure_wallboxes,
    fallback_name,
    refresh_station_names,
    update_hager_names,
    wallbox_id_of,
)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture
def client(database_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: database_session
    app.dependency_overrides[require_admin] = lambda: None

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def add_session(
    db: Session,
    wallbox_id: str | None,
    suffix: str,
    *,
    station_id: str = "ID: lang",
    invoiced: bool = False,
    start: datetime = datetime(2026, 8, 12, 10, 0),
) -> ChargingSession:
    session = ChargingSession(
        station_id=station_id,
        wallbox_id=wallbox_id,
        start_time=start,
        end_time=start.replace(hour=start.hour + 1),
        energy_total_kwh=1.0,
        energy_pv_kwh=0.5,
        invoiced=invoiced,
        import_hash=suffix * 64,
        source="hager",
    )
    db.add(session)
    db.commit()
    return session


# --------------------------------------------------------------------------
# Namen
# --------------------------------------------------------------------------
def test_fallback_uses_last_five_characters() -> None:
    assert fallback_name("C7Hkmi9cQsCdmZ4K4Uydb3") == "ID: ..Uydb3"
    assert fallback_name("AB1") == "ID: ..AB1"


def test_display_name_precedence() -> None:
    wallbox = Wallbox(wallbox_id="C7Hkmi9cQsCdmZ4K4Uydb3")
    assert display_name(wallbox) == "ID: ..Uydb3"

    wallbox.hager_name = "WB2"
    assert display_name(wallbox) == "WB2"

    wallbox.custom_name = "Garage links"
    assert display_name(wallbox) == "Garage links"


def test_hager_names_do_not_overwrite_custom_names(database_session: Session) -> None:
    database_session.add(Wallbox(wallbox_id="A", custom_name="Garage"))
    database_session.commit()

    update_hager_names(database_session, {"A": "WB1", "B": "WB2"})
    ensure_wallboxes(database_session, {"C"})
    database_session.commit()

    assert display_names(database_session) == {
        "A": "Garage",
        "B": "WB2",
        "C": "ID: ..C",
    }
    assert database_session.query(Wallbox).filter_by(wallbox_id="A").one().hager_name == "WB1"


def test_name_applies_only_to_unbilled_sessions(database_session: Session) -> None:
    wallbox = Wallbox(wallbox_id="W1", custom_name="Garage")
    database_session.add(wallbox)
    open_session = add_session(database_session, "W1", "a")
    billed = add_session(database_session, "W1", "b", invoiced=True)
    in_draft = add_session(database_session, "W1", "c")
    # stand in einer inzwischen stornierten Rechnung, ist wieder offen
    from_cancelled = add_session(database_session, "W1", "f")
    other = add_session(database_session, "W2", "d")

    invoice = Invoice(
        user_id=1,
        document_type="invoice",
        status="draft",
        issuer_name="X",
        issuer_address="Y",
        recipient_name="Z",
        recipient_address="Q",
        service_period_start=datetime(2026, 8, 1),
        service_period_end=datetime(2026, 9, 1),
        currency="EUR",
        total_net=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total_gross=Decimal("0.00"),
    )
    cancelled_invoice = Invoice(
        user_id=1,
        document_type="invoice",
        status="finalized",
        issuer_name="X",
        issuer_address="Y",
        recipient_name="Z",
        recipient_address="Q",
        service_period_start=datetime(2026, 7, 1),
        service_period_end=datetime(2026, 8, 1),
        currency="EUR",
        total_net=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total_gross=Decimal("0.00"),
    )
    database_session.add_all([invoice, cancelled_invoice])
    database_session.flush()

    def item(invoice_id: int, session_id: int) -> InvoiceItem:
        return InvoiceItem(
            invoice_id=invoice_id,
            item_type="charging_session",
            charging_session_id=session_id,
            position_number=1,
            description="Ladevorgang",
            net_amount=Decimal("0.00"),
            vat_rate=Decimal("19.00"),
            vat_amount=Decimal("0.00"),
            gross_amount=Decimal("0.00"),
        )

    database_session.add_all([
        item(invoice.id, in_draft.id),
        item(cancelled_invoice.id, from_cancelled.id),
    ])
    database_session.commit()

    assert apply_name_to_open_sessions(database_session, wallbox) == 2
    database_session.commit()

    for session in (open_session, billed, in_draft, from_cancelled, other):
        database_session.refresh(session)
    assert open_session.station_id == "Garage"
    assert from_cancelled.station_id == "Garage"
    assert billed.station_id == "ID: lang"
    assert in_draft.station_id == "ID: lang"
    assert other.station_id == "ID: lang"


# --------------------------------------------------------------------------
# Schnittstelle
# --------------------------------------------------------------------------
def test_list_and_rename_wallbox(client: TestClient, database_session: Session) -> None:
    database_session.add(Wallbox(wallbox_id="C7Hkmi9cQsCdmZ4K4Uydb3", hager_name=None))
    database_session.commit()
    add_session(database_session, "C7Hkmi9cQsCdmZ4K4Uydb3", "e")

    listed = client.get("/api/wallboxes").json()

    assert listed[0]["display_name"] == "ID: ..Uydb3"
    assert listed[0]["session_count"] == 1

    response = client.patch(
        f"/api/wallboxes/{listed[0]['id']}",
        json={"custom_name": "  Garage links  "},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Garage links"
    assert response.json()["updated_sessions"] == 1

    # leerer Name: wieder Name aus der Hager Cloud bzw. Kurzform
    response = client.patch(
        f"/api/wallboxes/{listed[0]['id']}",
        json={"custom_name": ""},
    )
    assert response.json()["custom_name"] is None
    assert response.json()["display_name"] == "ID: ..Uydb3"


def test_rename_unknown_wallbox_returns_404(client: TestClient) -> None:
    assert client.patch("/api/wallboxes/999", json={"custom_name": "X"}).status_code == 404


def test_custom_name_is_limited_to_100_characters(
    client: TestClient,
    database_session: Session,
) -> None:
    database_session.add(Wallbox(wallbox_id="W9"))
    database_session.commit()
    wallbox_id = database_session.query(Wallbox).one().id

    assert client.patch(
        f"/api/wallboxes/{wallbox_id}",
        json={"custom_name": "x" * 101},
    ).status_code == 422



def test_refresh_station_names_before_billing(database_session: Session) -> None:
    database_session.add(Wallbox(wallbox_id="W1", custom_name="Garage"))
    database_session.commit()
    known = add_session(database_session, "W1", "g", station_id="ID: W1")
    # ältere Daten: lange ID nur im Stationsnamen, keine Wallbox-ID
    legacy = add_session(database_session, None, "h", station_id="ID: C7Hkmi9cQsCdmZ4K4Uydb3")
    named = add_session(database_session, None, "i", station_id="WB2")

    assert wallbox_id_of(legacy) == "C7Hkmi9cQsCdmZ4K4Uydb3"
    assert wallbox_id_of(named) is None

    refresh_station_names(database_session, [known, legacy, named])

    assert known.station_id == "Garage"
    assert legacy.station_id == "ID: ..Uydb3"
    assert legacy.wallbox_id == "C7Hkmi9cQsCdmZ4K4Uydb3"
    assert named.station_id == "WB2"
    # die bisher unbekannte Wallbox erscheint in der Tabelle
    assert display_names(database_session)["C7Hkmi9cQsCdmZ4K4Uydb3"] == "ID: ..Uydb3"
