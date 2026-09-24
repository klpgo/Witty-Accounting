from collections.abc import Generator
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import require_admin
from app.database import Base
from app.main import app
from app.models.global_settings import GlobalSettings


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(
            GlobalSettings(
                id=1,
                monthly_base_fee_net=Decimal("0.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
            )
        )
        db.commit()
        yield db

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(database_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield database_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def store_access(db: Session) -> None:
    settings = db.get(GlobalSettings, 1)
    settings.hager_username = "user@example.com"
    settings.hager_password_encrypted = "verschluesselt"
    settings.hager_installation_id = "1000143617"
    db.commit()


def test_defaults(client: TestClient) -> None:
    data = client.get("/api/settings/hager").json()

    assert data["auto_import_enabled"] is False
    assert data["auto_import_interval_hours"] == 24
    assert data["auto_import_start_time"] == "03:00"
    assert data["auto_import_next_run_at"] is None
    assert data["auto_import_last_status"] is None


def test_enable_schedule(client: TestClient, database_session: Session) -> None:
    store_access(database_session)

    response = client.patch(
        "/api/settings/hager",
        json={
            "auto_import_enabled": True,
            "auto_import_interval_hours": 6,
            "auto_import_start_time": "02:30",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["auto_import_enabled"] is True
    assert data["auto_import_interval_hours"] == 6
    assert data["auto_import_start_time"] == "02:30"
    assert data["auto_import_next_run_at"] is not None


def test_enable_requires_complete_access(client: TestClient) -> None:
    response = client.patch(
        "/api/settings/hager",
        json={"auto_import_enabled": True},
    )

    assert response.status_code == 422
    assert "Installations-ID" in response.json()["detail"]
    assert client.get("/api/settings/hager").json()["auto_import_enabled"] is False


def test_clearing_password_while_enabled_is_rejected(
    client: TestClient,
    database_session: Session,
) -> None:
    store_access(database_session)
    client.patch("/api/settings/hager", json={"auto_import_enabled": True})

    response = client.patch(
        "/api/settings/hager",
        json={"clear_password": True},
    )

    assert response.status_code == 422
    assert client.get("/api/settings/hager").json()["password_configured"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"auto_import_interval_hours": 0},
        {"auto_import_interval_hours": 25},
        {"auto_import_start_time": "24:00"},
        {"auto_import_start_time": "3 Uhr"},
    ],
)
def test_invalid_schedule_is_rejected(client: TestClient, payload: dict) -> None:
    assert client.patch("/api/settings/hager", json=payload).status_code == 422


def test_last_run_is_returned_with_timezone(
    client: TestClient,
    database_session: Session,
) -> None:
    from datetime import datetime

    settings = database_session.get(GlobalSettings, 1)
    settings.hager_auto_import_last_started_at = datetime(2026, 9, 24, 12, 0, 0)
    settings.hager_auto_import_last_status = "success"
    settings.hager_auto_import_last_message = "2 neu, 3 übersprungen"
    database_session.commit()

    data = client.get("/api/settings/hager").json()

    assert data["auto_import_last_started_at"].startswith("2026-09-24T12:00:00")
    assert data["auto_import_last_started_at"].endswith(("Z", "+00:00"))
    assert data["auto_import_last_message"] == "2 neu, 3 übersprungen"
