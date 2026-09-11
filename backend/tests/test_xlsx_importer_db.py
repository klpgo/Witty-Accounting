from pathlib import Path
from datetime import datetime

from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard
from app.models.user import User
from app.services.importers.xlsx_importer import import_xlsx_to_db
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)

HEADERS = [
    "Startdatum",
    "Status",
    "Dauer",
    "Gesamte Energie (kWh)",
    "MID-zertifiziert",
    "Solarstrom (kWh)",
    "Solares Verhältnis",
    "Authentifizierung",
    "Ladestation",
]


def create_test_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active

    sheet.append(HEADERS)

    sheet.append(
        [
            "15.07.2026 11:26:37",
            "Beendet",
            "0h 0m 52s",
            1.25,
            "Ja",
            0.25,
            "20 %",
            "RFID Nr.1 (6AA972EA)",
            "WB2",
        ]
    )

    sheet.append(
        [
            "15.07.2026 12:00:00",
            "Beendet",
            "0h 1m 0s",
            0.5,
            "Ja",
            0,
            "0 %",
            "Keine Authentifizierung",
            "WB3",
        ]
    )

    workbook.save(path)
    workbook.close()


def create_database_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )

    Base.metadata.create_all(engine)

    return Session(engine)


def create_user_with_rfid(
    db: Session,
) -> tuple[RFIDCard, RFIDCardAssignment]:
    user = User(
        email="max.mustermann@example.invalid",
        password_hash="test-password-hash",
        first_name="Max",
        last_name="Mustermann",
        address=None,
        phone=None,
        invoice_delivery_email=False,
        invoice_delivery_post=False,
        active=True,
    )

    db.add(user)
    db.flush()

    rfid_card = RFIDCard(
        rfid_number="6AA972EA",
        description="RFID Nr.1",
        active=True,
    )

    db.add(rfid_card)
    db.flush()

    assignment = RFIDCardAssignment(
        rfid_card_id=rfid_card.id,
        user_id=user.id,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
        valid_to=None,
    )

    db.add(assignment)
    db.commit()
    db.refresh(rfid_card)
    db.refresh(assignment)

    return rfid_card, assignment


def test_import_xlsx_to_db_assigns_rfid_and_skips_duplicates(
    tmp_path: Path,
) -> None:
    xlsx_path = tmp_path / "hager-export.xlsx"
    create_test_workbook(xlsx_path)

    with create_database_session() as db:
        rfid_card, assignment = (
            create_user_with_rfid(db)
        )

        first_result = import_xlsx_to_db(
            db=db,
            path=xlsx_path,
        )

        assert first_result["read"] == 2
        assert first_result["imported"] == 2
        assert first_result["skipped"] == 0
        assert first_result["unknown_rfid_sessions"] == 0
        assert first_result["unknown_rfid_numbers"] == []

        sessions = db.scalars(
            select(ChargingSession).order_by(
                ChargingSession.start_time
            )
        ).all()

        assert len(sessions) == 2

        authenticated_session = sessions[0]
        unauthenticated_session = sessions[1]

        assert authenticated_session.rfid_card_id == rfid_card.id
        assert (
            authenticated_session.rfid_assignment_id
            == assignment.id
        )
        assert authenticated_session.station_id == "WB2"
        assert authenticated_session.source == "xlsx"
        assert authenticated_session.hager_session_id is None

        assert unauthenticated_session.rfid_card_id is None
        assert (
            unauthenticated_session.rfid_assignment_id
            is None
        )
        assert unauthenticated_session.station_id == "WB3"

        second_result = import_xlsx_to_db(
            db=db,
            path=xlsx_path,
        )

        assert second_result["read"] == 2
        assert second_result["imported"] == 0
        assert second_result["skipped"] == 2

        session_count = len(
            db.scalars(
                select(ChargingSession)
            ).all()
        )

        assert session_count == 2


def test_import_xlsx_to_db_reports_unknown_rfid(
    tmp_path: Path,
) -> None:
    xlsx_path = tmp_path / "unknown-rfid.xlsx"
    create_test_workbook(xlsx_path)

    with create_database_session() as db:
        result = import_xlsx_to_db(
            db=db,
            path=xlsx_path,
        )

        assert result["read"] == 2
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["unknown_rfid_sessions"] == 1
        assert result["unknown_rfid_numbers"] == [
            "6AA972EA"
        ]

        sessions = db.scalars(
            select(ChargingSession)
        ).all()

        assert len(sessions) == 2
        assert all(
            session.rfid_card_id is None
            for session in sessions
        )

        assert all(
            session.rfid_assignment_id is None
            for session in sessions
        )
