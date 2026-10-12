from app.database import SessionLocal
from app.services.pricing import price_charging_sessions


def main() -> None:
    with SessionLocal() as db:
        result = price_charging_sessions(
            db=db,
            overwrite=False,
        )

    print(f"Read:                    {result['read']}")
    print(f"Priced:                  {result['priced']}")
    print(f"Missing tariff:          {result['missing_price']}")
    print(f"Invalid energy values: {result['invalid_energy']}")


if __name__ == "__main__":
    main()
