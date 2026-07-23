from app.database import SessionLocal
from app.services.pricing import price_charging_sessions


def main() -> None:
    with SessionLocal() as db:
        result = price_charging_sessions(
            db=db,
            overwrite=False,
        )

    print(f"Gelesen:                 {result['read']}")
    print(f"Bepreist:                {result['priced']}")
    print(f"Fehlender Tarif:         {result['missing_price']}")
    print(f"Ungültige Energiemengen: {result['invalid_energy']}")


if __name__ == "__main__":
    main()
