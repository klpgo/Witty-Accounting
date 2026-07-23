from getpass import getpass

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User
from app.security import hash_password


MIN_PASSWORD_LENGTH = 12


def read_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("Dieses Feld darf nicht leer sein.")


def read_password() -> str:
    while True:
        password = getpass("Passwort: ")

        if len(password) < MIN_PASSWORD_LENGTH:
            print(
                "Das Passwort muss mindestens "
                f"{MIN_PASSWORD_LENGTH} Zeichen lang sein."
            )
            continue

        confirmation = getpass(
            "Passwort wiederholen: "
        )

        if password != confirmation:
            print("Die Passwörter stimmen nicht überein.")
            continue

        return password


def main() -> None:
    email = read_required(
        "E-Mail-Adresse: "
    ).lower()

    first_name = read_required(
        "Vorname: "
    )

    last_name = read_required(
        "Nachname: "
    )

    password = read_password()
    password_hash = hash_password(password)

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(
                User.email == email
            )
        )

        if user is None:
            user = User(
                email=email,
                password_hash=password_hash,
                salutation=None,
                first_name=first_name,
                last_name=last_name,
                address=None,
                phone=None,
                invoice_delivery_email=False,
                invoice_delivery_post=False,
                active=True,
                is_admin=True,
            )

            db.add(user)
            action = "angelegt"

        else:
            user.password_hash = password_hash
            user.first_name = first_name
            user.last_name = last_name
            user.active = True
            user.is_admin = True
            action = "aktualisiert"

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(user)

        print()
        print(f"Administrator {action}:")
        print(f"  ID:     {user.id}")
        print(f"  E-Mail: {user.email}")
        print(f"  Name:   {user.first_name} {user.last_name}")


if __name__ == "__main__":
    main()
