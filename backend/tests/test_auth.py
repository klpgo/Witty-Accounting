from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.user import User
from app.models.global_settings import GlobalSettings
from app.security import hash_password


TEST_PASSWORD = "correct-test-password"


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
def unauthenticated_client(
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
    is_admin: bool,
    active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(
            TEST_PASSWORD
        ),
        salutation=None,
        first_name="Test",
        last_name="User",
        address=None,
        phone=None,
        invoice_delivery_email=False,
        invoice_delivery_post=False,
        active=active,
        is_admin=is_admin,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def authorization_header(
    user: User,
) -> dict[str, str]:
    token = create_access_token(user)

    return {
        "Authorization": f"Bearer {token}",
    }


def test_login_returns_access_token(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    create_user(
        database_session,
        email="admin@example.com",
        is_admin=True,
    )

    response = unauthenticated_client.post(
        "/auth/token",
        data={
            "username": "ADMIN@EXAMPLE.COM",
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(
        body["access_token"],
        str,
    )
    assert body["access_token"]


def test_login_rejects_wrong_password(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    create_user(
        database_session,
        email="admin@example.com",
        is_admin=True,
    )

    response = unauthenticated_client.post(
        "/auth/token",
        data={
            "username": "admin@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": (
            "E-Mail-Adresse oder Passwort "
            "ist falsch."
        ),
    }
    assert response.headers[
        "www-authenticate"
    ] == "Bearer"


def test_reprice_requires_authentication(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.post(
        "/energy-prices/reprice"
    )

    assert response.status_code == 401
    assert response.headers[
        "www-authenticate"
    ] == "Bearer"


def test_reprice_rejects_invalid_token(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.post(
        "/energy-prices/reprice",
        headers={
            "Authorization": (
                "Bearer definitely-invalid"
            ),
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": (
            "Anmeldedaten konnten nicht "
            "validiert werden."
        ),
    }
    assert response.headers[
        "www-authenticate"
    ] == "Bearer"


def test_reprice_rejects_non_admin_user(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        is_admin=False,
    )

    response = unauthenticated_client.post(
        "/energy-prices/reprice",
        headers=authorization_header(user),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": (
            "Administratorrechte erforderlich."
        ),
    }


def test_reprice_accepts_admin_user(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        is_admin=True,
    )

    response = unauthenticated_client.post(
        "/energy-prices/reprice",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200
    assert response.json() == {
        "read": 0,
        "priced": 0,
        "missing_price": 0,
        "invalid_energy": 0,
        "skipped_invoiced": 0,
    }


def test_create_energy_price_requires_authentication(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.post(
        "/energy-prices",
        json={
            "valid_from": "2026-01-01T00:00:00",
            "grid_price_net": "0.3000",
            "pv_price_net": "0.1000",
            "vat_rate": "19.00",
        },
    )

    assert response.status_code == 401

def test_me_returns_authenticated_user(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        is_admin=True,
    )

    response = unauthenticated_client.get(
        "/auth/me",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": admin.id,
        "email": admin.email,
        "first_name": admin.first_name,
        "last_name": admin.last_name,
        "is_admin": True,
        "active": True,
    }


def test_me_requires_authentication(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.get(
        "/auth/me"
    )

    assert response.status_code == 401
    assert response.headers[
        "www-authenticate"
    ] == "Bearer"


def test_normal_user_can_login_without_maintenance_mode(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        is_admin=False,
    )

    response = unauthenticated_client.post(
        "/auth/token",
        data={
            "username": user.email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_maintenance_mode_rejects_normal_user_login(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    database_session.add(
        GlobalSettings(
            id=1,
            maintenance_mode=True,
        )
    )
    database_session.commit()

    user = create_user(
        database_session,
        email="user@example.com",
        is_admin=False,
    )

    response = unauthenticated_client.post(
        "/auth/token",
        data={
            "username": user.email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Der Wartungsmodus ist aktiv. "
            "Die Anmeldung ist derzeit nur für "
            "Administratoren möglich."
        ),
    }


def test_maintenance_mode_allows_admin_login(
    unauthenticated_client: TestClient,
    database_session: Session,
) -> None:
    database_session.add(
        GlobalSettings(
            id=1,
            maintenance_mode=True,
        )
    )
    database_session.commit()

    admin = create_user(
        database_session,
        email="admin@example.com",
        is_admin=True,
    )

    response = unauthenticated_client.post(
        "/auth/token",
        data={
            "username": admin.email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
