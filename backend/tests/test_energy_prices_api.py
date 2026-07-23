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

    app.dependency_overrides[get_db] = (
        override_get_db
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_list_energy_prices_is_initially_empty(
    client: TestClient,
) -> None:
    response = client.get("/energy-prices")

    assert response.status_code == 200
    assert response.json() == []


def test_create_energy_price(
    client: TestClient,
    database_session: Session,
) -> None:
    response = client.post(
        "/energy-prices",
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
        "/energy-prices",
        json={
            "valid_from": "2026-01-01T00:00:00",
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    second_response = client.post(
        "/energy-prices",
        json={
            "valid_from": "2026-07-01T00:00:00",
            "grid_price_net": "0.3500",
            "pv_price_net": "0.1200",
            "vat_rate": "19.00",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get("/energy-prices")

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
        "/energy-prices",
        json=payload,
    )

    second_response = client.post(
        "/energy-prices",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": (
            "Für diesen Gültigkeitszeitpunkt "
            "existiert bereits ein Tarif."
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
        "/energy-prices",
        json=payload,
    )

    assert response.status_code == 422
