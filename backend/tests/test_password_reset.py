from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.database import Base
from app.main import app
from app.models.global_settings import GlobalSettings
from app.models.password_reset_token import (
    PasswordResetToken,
)
from app.models.user import User
from app.security import (
    hash_password,
    verify_password,
)
from app.services.password_policy import PasswordPolicy
from app.services.password_reset import (
    PasswordResetConfiguration,
    build_password_reset_message,
    create_password_reset_token,
    generate_temporary_password,
    hash_reset_token,
    load_password_reset_configuration,
    sign_password_reset_message,
)
from app.utils.utc import utc_now


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
    email: str = "user@example.com",
    active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("Old-password1!"),
        first_name="Erika",
        last_name="Musterfrau",
        invoice_delivery_email=True,
        invoice_delivery_post=False,
        active=active,
        is_admin=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_password_reset_request_is_neutral(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user(database_session)
    issued_for: list[int] = []

    def fake_issue_password_reset(
        db: Session,
        *,
        user: User,
        purpose: str,
    ) -> None:
        del db, purpose
        issued_for.append(user.id)

    monkeypatch.setattr(
        "app.api.routes.auth.issue_password_reset",
        fake_issue_password_reset,
    )

    known_response = client.post(
        "/auth/password-reset/request",
        json={"email": " USER@example.com "},
    )
    unknown_response = client.post(
        "/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )

    assert known_response.status_code == 202
    assert unknown_response.status_code == 202
    assert known_response.json() == unknown_response.json()
    assert issued_for == [user.id]


def test_inactive_user_does_not_receive_reset(
    client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(
        database_session,
        active=False,
    )

    def unexpected_issue(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "No reset should be issued."
        )

    monkeypatch.setattr(
        "app.api.routes.auth.issue_password_reset",
        unexpected_issue,
    )

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 202


def test_reset_token_is_hashed_and_single_use(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(database_session)
    raw_token = create_password_reset_token(
        database_session,
        user=user,
    )
    database_session.commit()

    stored_token = database_session.scalar(
        select(PasswordResetToken)
    )

    assert stored_token is not None
    assert stored_token.token_hash == (
        hash_reset_token(raw_token)
    )
    assert raw_token not in stored_token.token_hash

    response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "New-password2!",
        },
    )

    assert response.status_code == 204
    database_session.refresh(user)
    database_session.refresh(stored_token)
    assert verify_password(
        "New-password2!",
        user.password_hash,
    )
    assert stored_token.used_at is not None

    reused_response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "Another-password3!",
        },
    )

    assert reused_response.status_code == 400
    database_session.refresh(user)
    assert verify_password(
        "New-password2!",
        user.password_hash,
    )


def test_new_token_invalidates_previous_token(
    database_session: Session,
) -> None:
    user = create_user(database_session)
    first_token = create_password_reset_token(
        database_session,
        user=user,
    )
    second_token = create_password_reset_token(
        database_session,
        user=user,
    )
    database_session.commit()

    first_stored_token = database_session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash
            == hash_reset_token(first_token)
        )
    )
    second_stored_token = database_session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash
            == hash_reset_token(second_token)
        )
    )

    assert first_stored_token is not None
    assert second_stored_token is not None
    assert first_stored_token.used_at is not None
    assert second_stored_token.used_at is None


def test_expired_reset_token_is_rejected(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(database_session)
    raw_token = create_password_reset_token(
        database_session,
        user=user,
    )
    stored_token = database_session.scalar(
        select(PasswordResetToken)
    )
    assert stored_token is not None
    stored_token.expires_at = (
        utc_now() - timedelta(seconds=1)
    )
    database_session.commit()

    response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "New-password2!",
        },
    )

    assert response.status_code == 400
    database_session.refresh(user)
    assert verify_password(
        "Old-password1!",
        user.password_hash,
    )


def test_reset_enforces_password_policy(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(database_session)
    raw_token = create_password_reset_token(
        database_session,
        user=user,
    )
    database_session.commit()

    response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "abcdefgh",
        },
    )

    assert response.status_code == 422
    database_session.refresh(user)
    assert verify_password(
        "Old-password1!",
        user.password_hash,
    )


def test_invitation_message_contains_reset_link(
    database_session: Session,
) -> None:
    user = create_user(database_session)
    database_session.add(
        GlobalSettings(
            id=1,
            frontend_base_url=(
                "https://accounting.example.com"
            ),
            password_reset_token_expire_minutes=45,
        )
    )
    database_session.commit()
    configuration = (
        load_password_reset_configuration(
            database_session
        )
    )

    message = build_password_reset_message(
        user=user,
        token="secret-reset-token",
        purpose="invitation",
        application_name="Witty-Accounting",
        sender_email="service@example.com",
        sender_name="Witty",
        configuration=configuration,
    )

    body = message.get_content()

    assert message["Subject"] == (
        "Ihr Zugang zu Witty-Accounting"
    )
    assert (
        "https://accounting.example.com/"
        "reset-password?token=secret-reset-token"
    ) in body
    assert "einmalig" in body
    assert "45 Minuten gültig" in body


def test_reset_token_uses_configured_expiry(
    database_session: Session,
) -> None:
    user = create_user(database_session)
    configuration = PasswordResetConfiguration(
        frontend_base_url="https://example.test",
        expire_minutes=15,
    )
    before = utc_now()

    create_password_reset_token(
        database_session,
        user=user,
        configuration=configuration,
    )

    stored_token = database_session.scalar(
        select(PasswordResetToken)
    )

    assert stored_token is not None
    assert stored_token.expires_at >= (
        before + timedelta(minutes=15)
    )
    assert stored_token.expires_at <= (
        utc_now() + timedelta(minutes=15)
    )


def test_generated_temporary_password_meets_policy() -> None:
    policy = PasswordPolicy(
        min_length=40,
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special=True,
    )

    password = generate_temporary_password(policy)

    assert len(password) >= 40
    assert any(character.isupper() for character in password)
    assert any(character.islower() for character in password)
    assert any(character.isdigit() for character in password)
    assert any(
        not character.isalnum()
        for character in password
    )


def test_password_email_uses_smime_when_enabled(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    del database_session
    message = build_password_reset_message(
        user=User(
            email="user@example.com",
            password_hash="not-used",
            first_name="Erika",
            last_name="Musterfrau",
        ),
        token="secret-reset-token",
        purpose="password_reset",
        application_name="Witty-Accounting",
        sender_email="service@example.com",
        sender_name="Witty",
    )
    pkcs12_path = tmp_path / "signing.p12"
    password_path = tmp_path / "password"

    monkeypatch.setattr(
        "app.services.password_reset.settings.mail_smime_enabled",
        True,
    )
    monkeypatch.setattr(
        "app.services.password_reset.settings.mail_smime_pkcs12_path",
        pkcs12_path,
    )
    monkeypatch.setattr(
        "app.services.password_reset.settings.mail_smime_pkcs12_password_file",
        password_path,
    )

    calls: list[tuple[str, object, object]] = []

    def fake_sign_message(
        *,
        message: object,
        sender_email: str,
        pkcs12_path: object,
        password_file: object,
    ) -> bytes:
        del message
        calls.append(
            (
                sender_email,
                pkcs12_path,
                password_file,
            )
        )
        return b"signed-message"

    monkeypatch.setattr(
        "app.services.password_reset.sign_message",
        fake_sign_message,
    )

    signed_message = sign_password_reset_message(
        message=message,
        sender_email="service@example.com",
    )

    assert signed_message == b"signed-message"
    assert calls == [
        (
            "service@example.com",
            pkcs12_path,
            password_path,
        )
    ]
