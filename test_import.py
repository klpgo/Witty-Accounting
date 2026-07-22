from app.database import SessionLocal
from app.services.importers.xlsx_importer import import_xlsx_to_db


def main() -> None:
    with SessionLocal() as db:
        result = import_xlsx_to_db(
            db,
            "beispiel.xlsx",
        )

    print(f"Gelesen:                 {result['read']}")
    print(f"Importiert:              {result['imported']}")
    print(f"Übersprungen:            {result['skipped']}")
    print(f"Unbekannte RFID-Vorgänge:{result['unknown_rfid_sessions']}")
    print("Unbekannte RFID-Karten:")

    for rfid_number in result["unknown_rfid_numbers"]:
        print(f"  - {rfid_number}")


if __name__ == "__main__":
    main()
