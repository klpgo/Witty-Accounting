from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.database import Base
from app.main import app
from app.models.energy_price import EnergyPrice

from datetime import datetime

from app.models.charging_session import ChargingSession

from app.auth import require_admin


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

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_list_energy_prices_is_initially_empty(
    client: TestClient,
) -> None:
    response = client.get("/api/energy-prices")

    assert response.status_code == 200
    assert response.json() == []


def test_create_energy_price(
    client: TestClient,
    database_session: Session,
) -> None:
    response = client.post(
        "/api/energy-prices",
        json={
            "valid_from": "2026-01-01T00:00:00",
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["valid_from"] == (
        "2026-01-01T00:00:00"
    )
    assert body["grid_price_net"] == "0.3000"
    assert body["pv_price_net"] == "0.1000"
    assert body["vat_rate"] == "19.00"

    stored_price = database_session.scalar(
        select(EnergyPrice)
    )

    assert stored_price is not None
    assert stored_price.grid_price_net == Decimal(
        "0.3000"
    )
    assert stored_price.pv_price_net == Decimal(
        "0.1000"
    )
    assert stored_price.vat_rate == Decimal(
        "19.00"
    )


def test_list_energy_prices_newest_first(
    client: TestClient,
) -> None:
    first_response = client.post(
        "/api/energy-prices",
        json={
            "valid_from": "2026-01-01T00:00:00",
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    second_response = client.post(
        "/api/energy-prices",
        json={
            "valid_from": "2026-07-01T00:00:00",
            "grid_price_net": "0.3500",
            "pv_price_net": "0.1200",
            "vat_rate": "19.00",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get("/api/energy-prices")

    assert response.status_code == 200

    prices = response.json()

    assert len(prices) == 2
    assert prices[0]["valid_from"] == (
        "2026-07-01T00:00:00"
    )
    assert prices[1]["valid_from"] == (
        "2026-01-01T00:00:00"
    )


def test_rejects_duplicate_valid_from(
    client: TestClient,
) -> None:
    payload = {
        "valid_from": "2026-01-01T00:00:00",
        "grid_price_net": "0.3000",
        "pv_price_net": "0.1000",
        "vat_rate": "19.00",
    }

    first_response = client.post(
        "/api/energy-prices",
        json=payload,
    )

    second_response = client.post(
        "/api/energy-prices",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": (
            "A tariff already exists for this validity date."
        )
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("grid_price_net", "-0.1000"),
        ("pv_price_net", "-0.1000"),
        ("vat_rate", "-1.00"),
        ("vat_rate", "101.00"),
    ],
)
def test_rejects_invalid_values(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    payload = {
        "valid_from": "2026-01-01T00:00:00",
        "grid_price_net": "0.3000",
        "pv_price_net": "0.1000",
        "vat_rate": "19.00",
    }

    payload[field] = value

    response = client.post(
        "/api/energy-prices",
        json=payload,
    )

    assert response.status_code == 422


def test_reprice_only_updates_uninvoiced_sessions(
    client: TestClient,
    database_session: Session,
) -> None:
    database_session.add(
        EnergyPrice(
            valid_from=datetime(2026, 1, 1),
            grid_price_net=Decimal("0.3000"),
            pv_price_net=Decimal("0.1000"),
            vat_rate=Decimal("19.00"),
        )
    )

    uninvoiced_session = ChargingSession(
        hager_session_id=None,
        station_id="WB2",
        start_time=datetime(2026, 6, 17, 10, 0),
        end_time=datetime(2026, 6, 17, 11, 0),
        rfid_card_id=None,
        energy_total_kwh=2.0,
        energy_pv_kwh=0.5,
        cost_grid_net=None,
        cost_pv_net=None,
        vat_rate=None,
        invoiced=False,
        invoice_id=None,
        import_hash="h" * 64,
        source="xlsx",
    )

    invoiced_session = ChargingSession(
        hager_session_id=None,
        station_id="WB3",
        start_time=datetime(2026, 6, 17, 12, 0),
        end_time=datetime(2026, 6, 17, 13, 0),
        rfid_card_id=None,
        energy_total_kwh=5.0,
        energy_pv_kwh=1.0,
        cost_grid_net=Decimal("7.7777"),
        cost_pv_net=Decimal("1.1111"),
        vat_rate=Decimal("7.00"),
        invoiced=True,
        invoice_id=123,
        import_hash="i" * 64,
        source="xlsx",
    )

    database_session.add_all(
        [
            uninvoiced_session,
            invoiced_session,
        ]
    )
    database_session.commit()

    response = client.post(
        "/api/energy-prices/reprice"
    )

    assert response.status_code == 200
    assert response.json() == {
        "read": 2,
        "priced": 1,
        "missing_price": 0,
        "invalid_energy": 0,
        "skipped_invoiced": 1,
    }

    database_session.refresh(
        uninvoiced_session
    )
    database_session.refresh(
        invoiced_session
    )

    assert uninvoiced_session.cost_grid_net == Decimal(
        "0.4500"
    )
    assert uninvoiced_session.cost_pv_net == Decimal(
        "0.0500"
    )
    assert uninvoiced_session.vat_rate == Decimal(
        "19.00"
    )

    assert invoiced_session.cost_grid_net == Decimal(
        "7.7777"
    )
    assert invoiced_session.cost_pv_net == Decimal(
        "1.1111"
    )
    assert invoiced_session.vat_rate == Decimal(
        "7.00"
    )


def test_current_energy_price_uses_latest_valid_tariff(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 12, 0),
    )

    database_session.add_all(
        [
            EnergyPrice(
                valid_from=datetime(2026, 1, 1),
                grid_price_net=Decimal("0.3000"),
                pv_price_net=Decimal("0.1000"),
                vat_rate=Decimal("19.00"),
            ),
            EnergyPrice(
                valid_from=datetime(2026, 8, 1),
                grid_price_net=Decimal("0.4000"),
                pv_price_net=Decimal("0.2000"),
                vat_rate=Decimal("19.00"),
            ),
        ]
    )
    database_session.commit()

    response = client.get(
        "/api/energy-prices/current"
    )

    assert response.status_code == 200
    assert response.json()["valid_from"] == (
        "2026-01-01T00:00:00"
    )
    assert response.json()["grid_price_net"] == (
        "0.3000"
    )


def test_current_energy_price_returns_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 12, 0),
    )

    response = client.get(
        "/api/energy-prices/current"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "There is no currently valid energy tariff yet."
        ),
    }


def test_unchanged_current_energy_price_is_not_duplicated(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 12, 0),
    )

    energy_price = EnergyPrice(
        valid_from=datetime(2026, 1, 1),
        grid_price_net=Decimal("0.3000"),
        pv_price_net=Decimal("0.1000"),
        vat_rate=Decimal("19.00"),
    )
    database_session.add(energy_price)
    database_session.commit()
    database_session.refresh(energy_price)

    response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == energy_price.id

    stored_prices = database_session.scalars(
        select(EnergyPrice)
    ).all()

    assert len(stored_prices) == 1


def test_changed_energy_price_creates_today_tariff(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 12, 0),
    )

    database_session.add(
        EnergyPrice(
            valid_from=datetime(2026, 1, 1),
            grid_price_net=Decimal("0.3000"),
            pv_price_net=Decimal("0.1000"),
            vat_rate=Decimal("19.00"),
        )
    )
    database_session.commit()

    response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3500",
            "pv_price_net": "0.1200",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 200
    assert response.json()["valid_from"] == (
        "2026-07-29T00:00:00"
    )
    assert response.json()["grid_price_net"] == (
        "0.3500"
    )
    assert response.json()["pv_price_net"] == (
        "0.1200"
    )

    stored_prices = database_session.scalars(
        select(EnergyPrice).order_by(
            EnergyPrice.valid_from
        )
    ).all()

    assert len(stored_prices) == 2


def test_reset_today_to_previous_price_removes_today_tariff(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 18, 0),
    )

    previous_price = EnergyPrice(
        valid_from=datetime(2026, 1, 1),
        grid_price_net=Decimal("0.3000"),
        pv_price_net=Decimal("0.1000"),
        vat_rate=Decimal("19.00"),
    )

    database_session.add(previous_price)
    database_session.commit()
    database_session.refresh(previous_price)

    changed_response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3500",
            "pv_price_net": "0.1200",
            "vat_rate": "19.00",
        },
    )

    assert changed_response.status_code == 200
    assert changed_response.json()["valid_from"] == (
        "2026-07-29T00:00:00"
    )

    reset_response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    assert reset_response.status_code == 200
    assert reset_response.json()["id"] == (
        previous_price.id
    )
    assert reset_response.json()["valid_from"] == (
        "2026-01-01T00:00:00"
    )

    stored_prices = list(
        database_session.scalars(
            select(EnergyPrice).order_by(
                EnergyPrice.valid_from
            )
        ).all()
    )

    assert len(stored_prices) == 1
    assert stored_prices[0].id == previous_price.id
    assert stored_prices[0].grid_price_net == Decimal(
        "0.3000"
    )



def test_first_energy_price_starts_today(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 23, 30),
    )

    response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3500",
            "pv_price_net": "0.1200",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 200
    assert response.json()["valid_from"] == (
        "2026-07-29T00:00:00"
    )

    stored_price = database_session.scalar(
        select(EnergyPrice)
    )

    assert stored_price is not None
    assert stored_price.valid_from == datetime(
        2026,
        7,
        29,
    )


def test_second_change_today_updates_existing_tariff(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.energy_prices.local_now",
        lambda: datetime(2026, 7, 29, 18, 0),
    )

    today_price = EnergyPrice(
        valid_from=datetime(2026, 7, 29),
        grid_price_net=Decimal("0.3500"),
        pv_price_net=Decimal("0.1200"),
        vat_rate=Decimal("19.00"),
    )
    future_price = EnergyPrice(
        valid_from=datetime(2026, 8, 1),
        grid_price_net=Decimal("0.5000"),
        pv_price_net=Decimal("0.2500"),
        vat_rate=Decimal("7.00"),
    )

    database_session.add_all(
        [
            today_price,
            future_price,
        ]
    )
    database_session.commit()
    database_session.refresh(today_price)
    database_session.refresh(future_price)

    response = client.put(
        "/api/energy-prices/current",
        json={
            "grid_price_net": "0.3700",
            "pv_price_net": "0.1300",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == today_price.id
    assert response.json()["grid_price_net"] == (
        "0.3700"
    )

    database_session.refresh(today_price)
    database_session.refresh(future_price)

    assert today_price.grid_price_net == Decimal(
        "0.3700"
    )
    assert today_price.pv_price_net == Decimal(
        "0.1300"
    )

    assert future_price.grid_price_net == Decimal(
        "0.5000"
    )
    assert future_price.pv_price_net == Decimal(
        "0.2500"
    )

    stored_prices = database_session.scalars(
        select(EnergyPrice)
    ).all()

    assert len(stored_prices) == 2


# --------------------------------------------------------------------------
# Gültigkeit ab einem Datum, Ändern und Schutz abgerechneter Zeiträume
# --------------------------------------------------------------------------
def add_invoice(db: Session, service_period_end: datetime) -> None:
    from app.models.invoice import Invoice

    db.add(
        Invoice(
            user_id=1,
            document_type="invoice",
            status="finalized",
            issuer_name="Wallbox GbR",
            issuer_address="Am Wolfsberg 42",
            recipient_name="Max Mustermann",
            recipient_address="Musterweg 1",
            service_period_start=datetime(2026, 8, 1),
            service_period_end=service_period_end,
            currency="EUR",
            total_net=Decimal("0.00"),
            vat_amount=Decimal("0.00"),
            total_gross=Decimal("0.00"),
        )
    )
    db.commit()


def add_price(db: Session, valid_from: datetime, grid: str = "0.3000") -> EnergyPrice:
    price = EnergyPrice(
        valid_from=valid_from,
        grid_price_net=Decimal(grid),
        pv_price_net=Decimal("0.1000"),
        vat_rate=Decimal("19.00"),
    )
    db.add(price)
    db.commit()
    return price


def add_session(db: Session, start: datetime, suffix: str) -> ChargingSession:
    session = ChargingSession(
        hager_session_id=None,
        station_id="WB2",
        start_time=start,
        end_time=start.replace(hour=start.hour + 1),
        rfid_card_id=None,
        energy_total_kwh=2.0,
        energy_pv_kwh=0.5,
        cost_grid_net=None,
        cost_pv_net=None,
        vat_rate=None,
        invoiced=False,
        invoice_id=None,
        import_hash=suffix * 64,
        source="xlsx",
    )
    db.add(session)
    db.commit()
    return session


PRICE = {"grid_price_net": "0.4000", "pv_price_net": "0.2000", "vat_rate": "19.00"}


def test_editable_from_follows_latest_invoice(
    client: TestClient,
    database_session: Session,
) -> None:
    assert client.get("/api/energy-prices/editable-from").json() == {
        "editable_from": None
    }

    add_invoice(database_session, datetime(2026, 9, 1))

    assert client.get("/api/energy-prices/editable-from").json() == {
        "editable_from": "2026-09-01T00:00:00"
    }


def test_past_price_is_rejected_within_invoiced_period(
    client: TestClient,
    database_session: Session,
) -> None:
    add_invoice(database_session, datetime(2026, 9, 1))

    rejected = client.post(
        "/api/energy-prices",
        json={"valid_from": "2026-08-15T00:00:00", **PRICE},
    )
    accepted = client.post(
        "/api/energy-prices",
        json={"valid_from": "2026-09-01T00:00:00", **PRICE},
    )

    assert rejected.status_code == 409
    assert "2026-09-01" in rejected.json()["detail"]
    assert accepted.status_code == 201


def test_past_price_reprices_uninvoiced_sessions(
    client: TestClient,
    database_session: Session,
) -> None:
    add_price(database_session, datetime(2026, 1, 1), grid="0.3000")
    before = add_session(database_session, datetime(2026, 8, 31, 10, 0), "a")
    after = add_session(database_session, datetime(2026, 9, 2, 10, 0), "b")

    response = client.post(
        "/api/energy-prices",
        json={"valid_from": "2026-09-01T00:00:00", **PRICE},
    )

    assert response.status_code == 201
    database_session.refresh(before)
    database_session.refresh(after)
    # vor dem Stichtag unverändert (nicht bepreist), danach neuer Preis
    assert before.cost_grid_net is None
    assert after.cost_grid_net == Decimal("0.6000")


def test_update_changes_date_and_prices_and_reprices(
    client: TestClient,
    database_session: Session,
) -> None:
    add_price(database_session, datetime(2026, 1, 1), grid="0.3000")
    price = add_price(database_session, datetime(2026, 10, 1), grid="0.5000")
    session = add_session(database_session, datetime(2026, 9, 15, 10, 0), "c")

    response = client.put(
        f"/api/energy-prices/{price.id}",
        json={"valid_from": "2026-09-01", **PRICE},
    )

    assert response.status_code == 200
    assert response.json()["valid_from"] == "2026-09-01T00:00:00"
    assert response.json()["grid_price_net"] == "0.4000"
    database_session.refresh(session)
    assert session.cost_grid_net == Decimal("0.6000")


def test_update_is_rejected_for_invoiced_period(
    client: TestClient,
    database_session: Session,
) -> None:
    old = add_price(database_session, datetime(2026, 8, 1))
    future = add_price(database_session, datetime(2026, 10, 1))
    add_invoice(database_session, datetime(2026, 9, 1))

    # alter Zeitpunkt liegt im abgerechneten Zeitraum
    assert client.put(
        f"/api/energy-prices/{old.id}",
        json={"valid_from": "2026-09-15", **PRICE},
    ).status_code == 409
    # neuer Zeitpunkt läge im abgerechneten Zeitraum
    assert client.put(
        f"/api/energy-prices/{future.id}",
        json={"valid_from": "2026-08-20", **PRICE},
    ).status_code == 409
    # innerhalb des offenen Zeitraums verschieben ist erlaubt
    assert client.put(
        f"/api/energy-prices/{future.id}",
        json={"valid_from": "2026-09-01", **PRICE},
    ).status_code == 200


def test_update_rejects_duplicate_date_and_unknown_tariff(
    client: TestClient,
    database_session: Session,
) -> None:
    add_price(database_session, datetime(2026, 9, 1))
    price = add_price(database_session, datetime(2026, 10, 1))

    assert client.put(
        f"/api/energy-prices/{price.id}",
        json={"valid_from": "2026-09-01", **PRICE},
    ).status_code == 409
    assert client.put(
        "/api/energy-prices/999999",
        json={"valid_from": "2026-11-01", **PRICE},
    ).status_code == 404
