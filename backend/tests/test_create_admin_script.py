from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.security import hash_password, verify_password
from scripts import create_admin


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


def configure_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    values: list[str],
    passwords: list[str] | None = None,
) -> None:
    entered_values = iter(values)
    entered_passwords = iter(passwords or [])

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: next(entered_values),
    )
    monkeypatch.setattr(
        create_admin,
        "getpass",
        lambda _prompt: next(entered_passwords),
    )


def add_user(
    db: Session,
    *,
    email: str,
    is_admin: bool,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(
            "Existing1!"
        ),
        salutation=None,
        first_name="Existing",
        last_name="User",
        address=None,
        phone=None,
        invoice_delivery_email=False,
        invoice_delivery_post=False,
        active=True,
        is_admin=is_admin,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_creates_first_admin(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_inputs(
        monkeypatch,
        values=[
            "ADMIN@EXAMPLE.COM",
            "Ada",
            "Admin",
        ],
        passwords=[
            "Sicheres1!",
            "Sicheres1!",
        ],
    )

    user = create_admin.create_first_admin(
        database_session
    )

    assert user.email == "admin@example.com"
    assert user.first_name == "Ada"
    assert user.last_name == "Admin"
    assert user.active is True
    assert user.is_admin is True
    assert verify_password(
        "Sicheres1!",
        user.password_hash,
    )


def test_refuses_when_admin_already_exists(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_admin = add_user(
        database_session,
        email="existing-admin@example.com",
        is_admin=True,
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: pytest.fail(
            "Es dürfen keine Daten abgefragt werden."
        ),
    )

    with pytest.raises(
        create_admin.BootstrapRefusedError,
        match="bereits mindestens ein Administrator",
    ):
        create_admin.create_first_admin(
            database_session
        )

    database_session.refresh(existing_admin)
    assert existing_admin.email == (
        "existing-admin@example.com"
    )
    assert existing_admin.is_admin is True


def test_refuses_to_promote_existing_user(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_user = add_user(
        database_session,
        email="user@example.com",
        is_admin=False,
    )
    original_password_hash = (
        existing_user.password_hash
    )

    configure_inputs(
        monkeypatch,
        values=["USER@EXAMPLE.COM"],
    )

    with pytest.raises(
        create_admin.BootstrapRefusedError,
        match="ändert keine vorhandenen Konten",
    ):
        create_admin.create_first_admin(
            database_session
        )

    database_session.refresh(existing_user)
    assert existing_user.is_admin is False
    assert existing_user.password_hash == (
        original_password_hash
    )


def test_applies_configured_password_policy(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_inputs(
        monkeypatch,
        values=[
            "admin@example.com",
            "Ada",
            "Admin",
        ],
        passwords=[
            "not-valid",
            "Sicheres1!",
            "Sicheres1!",
        ],
    )

    user = create_admin.create_first_admin(
        database_session
    )

    assert verify_password(
        "Sicheres1!",
        user.password_hash,
    )


def test_second_bootstrap_is_refused(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_inputs(
        monkeypatch,
        values=[
            "admin@example.com",
            "Ada",
            "Admin",
        ],
        passwords=[
            "Sicheres1!",
            "Sicheres1!",
        ],
    )
    first_admin = (
        create_admin.create_first_admin(
            database_session
        )
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: pytest.fail(
            "Es dürfen keine Daten abgefragt werden."
        ),
    )

    with pytest.raises(
        create_admin.BootstrapRefusedError,
        match="ohne Änderung abgebrochen",
    ):
        create_admin.create_first_admin(
            database_session
        )

    database_session.refresh(first_admin)
    assert first_admin.is_admin is True
