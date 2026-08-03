from collections.abc import Generator
from datetime import datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.charging_session import (
    ChargingSession,
)
from app.models.global_settings import GlobalSettings
from app.models.user import User
from app.security import hash_password
from app.version import BACKEND_VERSION


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


def create_user(db: Session) -> User:
    user = User(
        email="user@example.test",
        password_hash=hash_password(
            "correct-test-password"
        ),
        first_name="Test",
        last_name="User",
        active=True,
        is_admin=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def authorization_header(
    user: User,
) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {create_access_token(user)}"
        ),
    }


def add_charging_session(
    db: Session,
    *,
    session_id: str,
    start_time: datetime,
    end_time: datetime,
    invoiced: bool,
) -> None:
    db.add(
        ChargingSession(
            hager_session_id=session_id,
            station_id="Witty-1",
            start_time=start_time,
            end_time=end_time,
            energy_total_kwh=10.0,
            energy_pv_kwh=4.0,
            invoiced=invoiced,
        )
    )


def test_dashboard_reports_operational_data(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(database_session)

    database_session.add(
        GlobalSettings(
            id=1,
            maintenance_mode=True,
            dashboard_note=(
                "Die Abrechnung wird vorbereitet."
            ),
        )
    )

    add_charging_session(
        database_session,
        session_id="older-invoiced",
        start_time=datetime(2026, 7, 31, 20, 0),
        end_time=datetime(2026, 7, 31, 21, 0),
        invoiced=True,
    )
    add_charging_session(
        database_session,
        session_id="latest-uninvoiced",
        start_time=datetime(2026, 8, 1, 9, 0),
        end_time=datetime(2026, 8, 1, 10, 30),
        invoiced=False,
    )
    database_session.commit()

    response = client.get(
        "/api/dashboard",
        headers=authorization_header(user),
    )

    assert response.status_code == 200
    assert response.json() == {
        "server_status": "maintenance",
        "admin_note": (
            "Die Abrechnung wird vorbereitet."
        ),
        "latest_charging_session_at": (
            "2026-08-01T10:30:00"
        ),
        "invoiced_through": (
            "2026-07-31T21:00:00"
        ),
        "backend_version": BACKEND_VERSION,
    }


def test_dashboard_handles_missing_operational_data(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(database_session)

    response = client.get(
        "/api/dashboard",
        headers=authorization_header(user),
    )

    assert response.status_code == 200
    assert response.json() == {
        "server_status": "online",
        "admin_note": None,
        "latest_charging_session_at": None,
        "invoiced_through": None,
        "backend_version": BACKEND_VERSION,
    }


def test_dashboard_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/dashboard")

    assert response.status_code == 401
