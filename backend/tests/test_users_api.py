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
    last_name: str,
    is_admin: bool = False,
    active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash="not-used",
        salutation=None,
        first_name=first_name,
        last_name=last_name,
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


def test_list_users_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/users")

    assert response.status_code == 401
    assert response.headers[
        "www-authenticate"
    ] == "Bearer"


def test_list_users_rejects_non_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
    )

    response = client.get(
        "/users",
        headers=authorization_header(user),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": (
            "Administratorrechte erforderlich."
        ),
    }


def test_list_users_returns_sorted_users(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Zoe",
        last_name="Zulu",
        is_admin=True,
    )

    create_user(
        database_session,
        email="berta@example.com",
        first_name="Berta",
        last_name="Alpha",
    )

    create_user(
        database_session,
        email="anna-one@example.com",
        first_name="Anna",
        last_name="Alpha",
    )

    create_user(
        database_session,
        email="anna-two@example.com",
        first_name="Anna",
        last_name="Alpha",
        active=False,
    )

    response = client.get(
        "/users",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200

    body = response.json()

    assert [
        user["email"]
        for user in body
    ] == [
        "anna-one@example.com",
        "anna-two@example.com",
        "berta@example.com",
        "admin@example.com",
    ]

    assert body[0]["first_name"] == "Anna"
    assert body[0]["last_name"] == "Alpha"
    assert body[2]["first_name"] == "Berta"
    assert body[3]["is_admin"] is True
    assert body[1]["active"] is False

    for user in body:
        assert "password_hash" not in user
        assert "id" in user
        assert "created_at" in user
        assert "updated_at" in user
