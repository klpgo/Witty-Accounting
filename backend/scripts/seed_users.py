from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.rfid_card import RFIDCard
from app.models.user import User


# Temporärer Hash für Entwicklungsbenutzer.
# Diese Benutzer sind nicht für eine echte Anmeldung vorgesehen.
SEED_PASSWORD_HASH = "!development-seed-user-no-login!"


USER_SEEDS = [
    {
        "email": "max.mustermann@example.invalid",
        "first_name": "Max",
        "last_name": "Mustermann",
        "cards": [
            ("6AA972EA", "RFID Nr.1"),
        ],
    },
    {
        "email": "erika.musterfrau@example.invalid",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "cards": [
            ("3027ECAC", "RFID Nr.2"),
            ("D0BEEEAC", "RFID Nr.3"),
        ],
    },
    {
        "email": "testnutzer4@example.invalid",
        "first_name": "Testnutzer",
        "last_name": "4",
        "cards": [
            ("6005E5AC", "RFID Nr.4"),
        ],
    },
    {
        "email": "testnutzer5@example.invalid",
        "first_name": "Testnutzer",
        "last_name": "5",
        "cards": [
            ("E033F68C", "RFID Nr.5"),
        ],
    },
    {
        "email": "testnutzer6@example.invalid",
        "first_name": "Testnutzer",
        "last_name": "6",
        "cards": [
            ("AA37FCF3", "RFID Nr.6"),
        ],
    },
    {
        "email": "testnutzer10@example.invalid",
        "first_name": "Testnutzer",
        "last_name": "10",
        "cards": [
            ("8A7704F4", "RFID Nr.10"),
        ],
    },
    {
        "email": "wartung.gottschalk@example.invalid",
        "first_name": "Wartung",
        "last_name": "Gottschalk",
        "cards": [
            ("DE0D02A6", "Wartung Gottschalk"),
        ],
    },
]


def seed_users(db: Session) -> dict[str, int]:
    created_users = 0
    created_cards = 0
    updated_cards = 0

    for user_seed in USER_SEEDS:
        user = db.scalar(
            select(User).where(
                User.email == user_seed["email"]
            )
        )

        if user is None:
            user = User(
                email=user_seed["email"],
                password_hash=SEED_PASSWORD_HASH,
                first_name=user_seed["first_name"],
                last_name=user_seed["last_name"],
                address=None,
                phone=None,
                invoice_delivery_email=False,
                invoice_delivery_post=False,
                active=True,
            )

            db.add(user)
            db.flush()

            created_users += 1

        for rfid_number, description in user_seed["cards"]:
            rfid_card = db.scalar(
                select(RFIDCard).where(
                    RFIDCard.rfid_number == rfid_number
                )
            )

            if rfid_card is None:
                rfid_card = RFIDCard(
                    user_id=user.id,
                    rfid_number=rfid_number,
                    description=description,
                    active=True,
                )

                db.add(rfid_card)
                created_cards += 1
                continue

            changed = False

            if rfid_card.user_id != user.id:
                rfid_card.user_id = user.id
                changed = True

            if rfid_card.description != description:
                rfid_card.description = description
                changed = True

            if not rfid_card.active:
                rfid_card.active = True
                changed = True

            if changed:
                updated_cards += 1

    db.commit()

    return {
        "created_users": created_users,
        "created_cards": created_cards,
        "updated_cards": updated_cards,
    }


def main() -> None:
    with SessionLocal() as db:
        try:
            result = seed_users(db)
        except Exception:
            db.rollback()
            raise

    print(f"Benutzer angelegt:       {result['created_users']}")
    print(f"RFID-Karten angelegt:    {result['created_cards']}")
    print(f"RFID-Karten aktualisiert:{result['updated_cards']}")


if __name__ == "__main__":
    main()
