from collections.abc import Iterator
from contextlib import contextmanager
from getpass import getpass

from sqlalchemy import Connection, select, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.user import User
from app.security import hash_password
from app.services.password_policy import (
    PasswordPolicy,
    PasswordPolicyError,
    load_password_policy,
    validate_password,
)


BOOTSTRAP_LOCK_NAME = (
    "witty-accounting-create-first-admin"
)
BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 10


class BootstrapRefusedError(RuntimeError):
    """Der erste Administrator darf nicht angelegt werden."""


def read_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("Dieses Feld darf nicht leer sein.")


def read_password(
    policy: PasswordPolicy,
) -> str:
    while True:
        password = getpass("Passwort: ")

        try:
            validate_password(
                password,
                policy,
            )
        except PasswordPolicyError as exc:
            print(str(exc))
            continue

        confirmation = getpass(
            "Passwort wiederholen: "
        )

        if password != confirmation:
            print("Die Passwörter stimmen nicht überein.")
            continue

        return password


@contextmanager
def bootstrap_lock(
    connection: Connection,
) -> Iterator[None]:
    uses_named_lock = (
        connection.dialect.name
        in {"mysql", "mariadb"}
    )

    if uses_named_lock:
        acquired = connection.execute(
            text(
                "SELECT GET_LOCK("
                ":lock_name, :timeout_seconds"
                ")"
            ),
            {
                "lock_name": BOOTSTRAP_LOCK_NAME,
                "timeout_seconds": (
                    BOOTSTRAP_LOCK_TIMEOUT_SECONDS
                ),
            },
        ).scalar_one()

        if acquired != 1:
            raise BootstrapRefusedError(
                "Der Bootstrap ist bereits in "
                "einem anderen Prozess aktiv."
            )

    try:
        yield
    finally:
        if uses_named_lock:
            connection.execute(
                text(
                    "SELECT RELEASE_LOCK("
                    ":lock_name"
                    ")"
                ),
                {
                    "lock_name": (
                        BOOTSTRAP_LOCK_NAME
                    ),
                },
            )


def ensure_no_admin_exists(
    db: Session,
) -> None:
    admin_id = db.scalar(
        select(User.id)
        .where(User.is_admin.is_(True))
        .limit(1)
    )

    if admin_id is not None:
        raise BootstrapRefusedError(
            "Es existiert bereits mindestens ein "
            "Administrator. Der Bootstrap wurde "
            "ohne Änderung abgebrochen."
        )


def ensure_email_is_available(
    db: Session,
    email: str,
) -> None:
    existing_user_id = db.scalar(
        select(User.id).where(
            User.email == email
        )
    )

    if existing_user_id is not None:
        raise BootstrapRefusedError(
            "Für diese E-Mail-Adresse existiert "
            "bereits ein Benutzer. Der Bootstrap "
            "ändert keine vorhandenen Konten."
        )


def create_first_admin_with_values(
    db: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
) -> User:
    ensure_no_admin_exists(db)
    normalized_email = email.strip().lower()

    if not normalized_email:
        raise BootstrapRefusedError(
            "Die E-Mail-Adresse darf nicht leer sein."
        )

    normalized_first_name = first_name.strip()
    normalized_last_name = last_name.strip()

    if not normalized_first_name or not normalized_last_name:
        raise BootstrapRefusedError(
            "Vor- und Nachname dürfen nicht leer sein."
        )

    ensure_email_is_available(
        db,
        normalized_email,
    )

    validate_password(
        password,
        load_password_policy(db),
    )
    password_hash = hash_password(password)

    user = User(
        email=normalized_email,
        password_hash=password_hash,
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        address=None,
        phone=None,
        invoice_delivery_email=False,
        invoice_delivery_post=False,
        active=True,
        is_admin=True,
    )

    db.add(user)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user)

    return user


def create_first_admin(
    db: Session,
) -> User:
    ensure_no_admin_exists(db)
    email = read_required(
        "E-Mail-Adresse: "
    ).lower()
    ensure_email_is_available(db, email)
    first_name = read_required(
        "Vorname: "
    )
    last_name = read_required(
        "Nachname: "
    )
    password = read_password(
        load_password_policy(db)
    )

    return create_first_admin_with_values(
        db,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )


def main() -> None:
    try:
        with engine.connect() as connection:
            with bootstrap_lock(connection):
                # The named lock belongs to the lock connection,
                # not to its transaction.  Keep the application
                # transaction on a separate Session connection:
                # GET_LOCK() starts an outer SQLAlchemy transaction
                # and a Session bound to that connection cannot
                # commit it.  Closing the lock connection would then
                # roll the newly inserted administrator back.
                with SessionLocal() as db:
                    user = create_first_admin(db)
    except BootstrapRefusedError as exc:
        raise SystemExit(str(exc)) from exc

    print()
    print("Erster Administrator angelegt:")
    print(f"  ID:     {user.id}")
    print(f"  E-Mail: {user.email}")
    print(
        "  Name:   "
        f"{user.first_name} {user.last_name}"
    )


if __name__ == "__main__":
    main()
