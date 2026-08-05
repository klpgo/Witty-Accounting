from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.user import User
from app.models.global_settings import GlobalSettings

from app.security import (
    hash_password,
    verify_password,
)
from app.services.password_reset import (
    PasswordResetEmailError,
)

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
    password: str | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=(
            hash_password(password)
            if password is not None
            else "not-used"
        ),
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
    response = client.get("/api/users")

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
        "/api/users",
        headers=authorization_header(user),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": (
            "Administratorrechte erforderlich."
        ),
    }


def test_create_user_requires_authentication(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/users",
        json={
            "email": "new@example.com",
            "first_name": "Neue",
            "last_name": "Person",
            "password": "StrongPass1!",
        },
    )

    assert response.status_code == 401


def test_create_user_rejects_non_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
    )

    response = client.post(
        "/api/users",
        headers=authorization_header(user),
        json={
            "email": "new@example.com",
            "first_name": "Neue",
            "last_name": "Person",
            "password": "StrongPass1!",
        },
    )

    assert response.status_code == 403


def test_admin_creates_user(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitations: list[tuple[int, str]] = []

    def fake_issue_password_reset(
        db: Session,
        *,
        user: User,
        purpose: str,
    ) -> None:
        del db
        invitations.append((user.id, purpose))

    monkeypatch.setattr(
        "app.api.routes.users.issue_password_reset",
        fake_issue_password_reset,
    )

    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    response = client.post(
        "/api/users",
        headers=authorization_header(admin),
        json={
            "email": " NEW@example.com ",
            "salutation": " Frau ",
            "first_name": " Erika ",
            "last_name": " Musterfrau ",
            "address": " Musterstraße 1 ",
            "phone": " +49 123 456 ",
            "invoice_delivery_email": True,
            "invoice_delivery_post": False,
            "active": True,
            "is_admin": False,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == "new@example.com"
    assert body["salutation"] == "Frau"
    assert body["first_name"] == "Erika"
    assert body["last_name"] == "Musterfrau"
    assert body["address"] == "Musterstraße 1"
    assert body["phone"] == "+49 123 456"
    assert body["active"] is True
    assert body["is_admin"] is False
    assert "password_hash" not in body

    created_user = database_session.get(
        User,
        body["id"],
    )

    assert created_user is not None
    assert created_user.password_hash != "not-used"
    assert not verify_password(
        "StrongPass1!",
        created_user.password_hash,
    )
    assert invitations == [
        (created_user.id, "invitation"),
    ]


def test_rejects_combined_email_and_post_delivery(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    response = client.post(
        "/api/users",
        headers=authorization_header(admin),
        json={
            "email": "new@example.com",
            "first_name": "Neue",
            "last_name": "Person",
            "invoice_delivery_email": True,
            "invoice_delivery_post": True,
        },
    )

    assert response.status_code == 422
    assert "genau eine" in response.json()["detail"]


def test_user_creation_rolls_back_if_invitation_fails(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    def fail_invitation(
        db: Session,
        *,
        user: User,
        purpose: str,
    ) -> None:
        del db, user, purpose
        raise PasswordResetEmailError(
            "SMTP unavailable"
        )

    monkeypatch.setattr(
        "app.api.routes.users.issue_password_reset",
        fail_invitation,
    )

    response = client.post(
        "/api/users",
        headers=authorization_header(admin),
        json={
            "email": "new@example.com",
            "first_name": "Neue",
            "last_name": "Person",
        },
    )

    assert response.status_code == 503
    assert database_session.scalar(
        select(User).where(
            User.email == "new@example.com"
        )
    ) is None


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
        "/api/users",
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
        assert "last_login" in user
        assert "created_at" in user
        assert "updated_at" in user


def test_get_own_profile_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/users/me")

    assert response.status_code == 401


def test_get_own_profile(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Max",
        last_name="Mustermann",
    )

    response = client.get(
        "/api/users/me",
        headers=authorization_header(user),
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert (
        response.json()["email"]
        == "user@example.com"
    )
    assert "password_hash" not in response.json()


def test_updates_own_profile(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="old@example.com",
        first_name="Max",
        last_name="Mustermann",
    )

    response = client.patch(
        "/api/users/me",
        headers=authorization_header(user),
        json={
            "email": "NEW@example.com",
            "salutation": " Frau ",
            "first_name": " Erika ",
            "last_name": " Musterfrau ",
            "address": (
                "Musterstraße 2\n"
                "12345 Musterstadt"
            ),
            "phone": " +49 123 456 ",
            "invoice_delivery_email": False,
            "invoice_delivery_post": True,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["email"] == "new@example.com"
    assert body["first_name"] == "Erika"
    assert body["last_name"] == "Musterfrau"
    assert body["address"] == (
        "Musterstraße 2\n"
        "12345 Musterstadt"
    )
    assert body["salutation"] == "Frau"
    assert body["phone"] == "+49 123 456"
    assert body["invoice_delivery_email"] is False
    assert body["invoice_delivery_post"] is True

    database_session.refresh(user)

    assert user.email == "new@example.com"
    assert user.first_name == "Erika"
    assert user.last_name == "Musterfrau"
    assert user.salutation == "Frau"
    assert user.phone == "+49 123 456"
    assert user.invoice_delivery_email is False
    assert user.invoice_delivery_post is True


def test_update_own_profile_rejects_duplicate_email(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
    )

    create_user(
        database_session,
        email="used@example.com",
        first_name="Other",
        last_name="User",
    )

    response = client.patch(
        "/api/users/me",
        headers=authorization_header(user),
        json={
            "email": "USED@example.com",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Diese E-Mail-Adresse wird "
            "bereits verwendet."
        ),
    }


def test_update_own_profile_rejects_admin_fields(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
    )

    response = client.patch(
        "/api/users/me",
        headers=authorization_header(user),
        json={
            "is_admin": True,
            "active": False,
        },
    )

    assert response.status_code == 422

    database_session.refresh(user)

    assert user.is_admin is False
    assert user.active is True


def test_changes_own_password(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
        password="old-password",
    )

    response = client.post(
        "/api/users/me/password",
        headers=authorization_header(user),
        json={
            "current_password": "old-password",
            "new_password": "New-password1!",
        },
    )

    assert response.status_code == 204
    assert response.content == b""

    database_session.refresh(user)

    assert verify_password(
        "New-password1!",
        user.password_hash,
    )
    assert not verify_password(
        "old-password",
        user.password_hash,
    )


def test_change_own_password_rejects_weak_password(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
        password="old-password",
    )

    original_password_hash = user.password_hash

    response = client.post(
        "/api/users/me/password",
        headers=authorization_header(user),
        json={
            "current_password": "old-password",
            "new_password": "abcdefgh",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Das Passwort muss einen "
            "Großbuchstaben, eine Zahl und "
            "ein Sonderzeichen enthalten."
        ),
    }

    database_session.refresh(user)

    assert (
        user.password_hash
        == original_password_hash
    )


def test_change_own_password_rejects_wrong_password(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
        password="old-password",
    )

    original_password_hash = user.password_hash

    response = client.post(
        "/api/users/me/password",
        headers=authorization_header(user),
        json={
            "current_password": "wrong-password",
            "new_password": "new-password",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Das aktuelle Passwort ist "
            "nicht korrekt."
        ),
    }

    database_session.refresh(user)

    assert (
        user.password_hash
        == original_password_hash
    )


def test_get_user_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
        last_name="User",
    )

    response = client.get(
        f"/api/users/{target.id}",
        headers=authorization_header(user),
    )

    assert response.status_code == 403


def test_admin_gets_user(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
        last_name="User",
    )

    response = client.get(
        f"/api/users/{target.id}",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200
    assert response.json()["id"] == target.id
    assert (
        response.json()["email"]
        == "target@example.com"
    )
    assert "password_hash" not in response.json()


def test_admin_updates_user(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="old@example.com",
        first_name="Old",
        last_name="Name",
    )

    response = client.patch(
        f"/api/users/{target.id}",
        headers=authorization_header(admin),
        json={
            "email": "NEW@example.com",
            "first_name": " Erika ",
            "last_name": " Musterfrau ",
            "address": (
                "Musterstraße 5\n"
                "12345 Musterstadt"
            ),
            "invoice_delivery_email": False,
            "invoice_delivery_post": False,
            "active": False,
            "is_admin": True,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["email"] == "new@example.com"
    assert body["first_name"] == "Erika"
    assert body["last_name"] == "Musterfrau"
    assert body["active"] is False
    assert body["is_admin"] is True

    database_session.refresh(target)

    assert target.email == "new@example.com"
    assert target.first_name == "Erika"
    assert target.last_name == "Musterfrau"
    assert target.invoice_delivery_email is False
    assert target.invoice_delivery_post is False
    assert target.active is False
    assert target.is_admin is True


def test_admin_update_rejects_duplicate_email(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
        last_name="User",
    )

    create_user(
        database_session,
        email="used@example.com",
        first_name="Used",
        last_name="User",
    )

    response = client.patch(
        f"/api/users/{target.id}",
        headers=authorization_header(admin),
        json={
            "email": "USED@example.com",
        },
    )

    assert response.status_code == 409


def test_admin_resets_user_password(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
        last_name="User",
        password="old-password",
    )

    response = client.post(
        f"/api/users/{target.id}/password",
        headers=authorization_header(admin),
        json={
            "new_password": "New-password1!",
        },
    )

    assert response.status_code == 204
    assert response.content == b""

    database_session.refresh(target)

    assert verify_password(
        "New-password1!",
        target.password_hash,
    )
    assert not verify_password(
        "old-password",
        target.password_hash,
    )


def test_admin_password_reset_rejects_weak_password(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
        last_name="User",
        password="old-password",
    )

    original_password_hash = target.password_hash

    response = client.post(
        f"/api/users/{target.id}/password",
        headers=authorization_header(admin),
        json={
            "new_password": "abcdefgh",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Das Passwort muss einen "
            "Großbuchstaben, eine Zahl und "
            "ein Sonderzeichen enthalten."
        ),
    }

    database_session.refresh(target)

    assert (
        target.password_hash
        == original_password_hash
    )


def test_password_change_uses_saved_policy(
    client: TestClient,
    database_session: Session,
) -> None:
    database_session.add(
        GlobalSettings(
            id=1,
            password_min_length=8,
            password_require_uppercase=False,
            password_require_lowercase=True,
            password_require_digit=False,
            password_require_special=False,
        )
    )
    database_session.commit()

    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
        last_name="User",
        password="old-password",
    )

    response = client.post(
        "/api/users/me/password",
        headers=authorization_header(user),
        json={
            "current_password": "old-password",
            "new_password": "abcdefgh",
        },
    )

    assert response.status_code == 204

    database_session.refresh(user)

    assert verify_password(
        "abcdefgh",
        user.password_hash,
    )


def test_admin_user_routes_return_not_found(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )

    response = client.get(
        "/api/users/999999",
        headers=authorization_header(admin),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Benutzer 999999 wurde nicht "
            "gefunden."
        ),
    }
