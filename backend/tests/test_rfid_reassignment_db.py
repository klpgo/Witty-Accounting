from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import RFIDCardAssignment
from app.models.user import User
from app.services.importers.hager_json_importer import (
    import_items_to_db,
)
from app.services.rfid_reassignment import (
    ASSIGNED,
    INACTIVE_CARD,
    NO_ASSIGNMENT,
    UNKNOWN_CARD,
    classify_rfid,
    reassign_open_sessions,
)


# 2026-07-15 09:26:37 UTC = 11:26:37 Ortszeit
SESSION_START_LOCAL = datetime(2026, 7, 15, 11, 26, 37)


def create_database_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def create_user(db: Session) -> User:
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
    return user


def create_card(db: Session, number: str, active: bool = True) -> RFIDCard:
    card = RFIDCard(rfid_number=number, description=number, active=active)
    db.add(card)
    db.flush()
    return card


def assign(
    db: Session,
    card: RFIDCard,
    user: User,
    valid_from: datetime,
) -> RFIDCardAssignment:
    assignment = RFIDCardAssignment(
        rfid_card_id=card.id,
        user_id=user.id,
        valid_from=valid_from,
        valid_to=None,
    )
    db.add(assignment)
    db.flush()
    return assignment


def hager_item(session_id: str, token: str | None) -> dict:
    return {
        "session": {
            "id": session_id,
            "kwh": 5.0,
            "start_date_time": "2026-07-15T09:26:37Z",
            "end_date_time": "2026-07-15T10:26:37Z",
        },
        "wallboxId": f"WB-{session_id}",
        "wallboxName": f"WB-{session_id}",
        "emobilityToken": token,
        "energySolar": 0.0,
    }


def test_classify_rfid_distinguishes_causes() -> None:
    with create_database_session() as db:
        user = create_user(db)
        assigned_card = create_card(db, "AAAA0001")
        create_card(db, "BBBB0002")
        create_card(db, "CCCC0003", active=False)
        assign(db, assigned_card, user, datetime(2026, 1, 1))

        assert classify_rfid(db, "AAAA0001", SESSION_START_LOCAL)[0] == ASSIGNED
        assert classify_rfid(db, "BBBB0002", SESSION_START_LOCAL)[0] == NO_ASSIGNMENT
        assert classify_rfid(db, "CCCC0003", SESSION_START_LOCAL)[0] == INACTIVE_CARD
        assert classify_rfid(db, "DDDD0004", SESSION_START_LOCAL)[0] == UNKNOWN_CARD


def test_classify_rfid_assignment_starting_after_session() -> None:
    with create_database_session() as db:
        user = create_user(db)
        card = create_card(db, "AAAA0001")
        assign(db, card, user, datetime(2026, 8, 1))

        assert classify_rfid(db, "AAAA0001", SESSION_START_LOCAL)[0] == NO_ASSIGNMENT


def test_import_reports_causes_and_stores_rfid_number() -> None:
    with create_database_session() as db:
        user = create_user(db)
        assigned_card = create_card(db, "AAAA0001")
        create_card(db, "BBBB0002")
        create_card(db, "CCCC0003", active=False)
        assign(db, assigned_card, user, datetime(2026, 1, 1))
        db.commit()

        result = import_items_to_db(
            db,
            [
                hager_item("s1", "AAAA0001"),
                hager_item("s2", "bbbb0002"),
                hager_item("s3", "CCCC0003"),
                hager_item("s4", "DDDD0004"),
                hager_item("s5", None),
            ],
        )

        assert result["imported"] == 5
        assert result["unknown_rfid_sessions"] == 3
        assert result["unknown_rfid_numbers"] == [
            "BBBB0002",
            "CCCC0003",
            "DDDD0004",
        ]
        assert result["unknown_rfid_cards"] == ["DDDD0004"]
        assert result["inactive_rfid_cards"] == ["CCCC0003"]
        assert result["unassigned_rfid_numbers"] == ["BBBB0002"]

        sessions = {
            s.hager_session_id: s
            for s in db.scalars(select(ChargingSession)).all()
        }

        assert sessions["s1"].rfid_number == "AAAA0001"
        assert sessions["s1"].rfid_card_id == assigned_card.id
        assert sessions["s2"].rfid_number == "BBBB0002"
        assert sessions["s2"].rfid_assignment_id is None
        assert sessions["s5"].rfid_number is None


def test_reassign_after_assignment_is_created() -> None:
    with create_database_session() as db:
        user = create_user(db)
        card = create_card(db, "BBBB0002")
        db.commit()

        import_items_to_db(db, [hager_item("s1", "BBBB0002")])

        charging_session = db.scalar(select(ChargingSession))
        assert charging_session.rfid_assignment_id is None

        assignment = assign(db, card, user, datetime(2026, 7, 1))
        db.commit()

        assert reassign_open_sessions(db) == 1
        db.commit()
        db.refresh(charging_session)

        assert charging_session.rfid_card_id == card.id
        assert charging_session.rfid_assignment_id == assignment.id


def test_reassign_skips_invoiced_sessions() -> None:
    with create_database_session() as db:
        user = create_user(db)
        card = create_card(db, "BBBB0002")
        db.commit()

        import_items_to_db(db, [hager_item("s1", "BBBB0002")])

        charging_session = db.scalar(select(ChargingSession))
        charging_session.invoiced = True
        assign(db, card, user, datetime(2026, 7, 1))
        db.commit()

        assert reassign_open_sessions(db) == 0
        db.refresh(charging_session)
        assert charging_session.rfid_assignment_id is None


def test_reimport_backfills_rfid_number_and_reassigns() -> None:
    with create_database_session() as db:
        user = create_user(db)
        card = create_card(db, "BBBB0002")
        assignment = assign(db, card, user, datetime(2026, 7, 1))

        # Ladevorgang aus einem älteren Import: ohne RFID-Nummer
        db.add(
            ChargingSession(
                hager_session_id="s1",
                station_id="WB-s1",
                start_time=SESSION_START_LOCAL,
                end_time=datetime(2026, 7, 15, 12, 26, 37),
                rfid_number=None,
                rfid_card_id=None,
                rfid_assignment_id=None,
                energy_total_kwh=5.0,
                energy_pv_kwh=0.0,
                invoiced=False,
                invoice_id=None,
                import_hash="x" * 64,
                source="json",
            )
        )
        db.commit()

        result = import_items_to_db(db, [hager_item("s1", "BBBB0002")])

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert result["backfilled_rfid_numbers"] == 1
        assert result["reassigned_sessions"] == 1

        charging_session = db.scalar(select(ChargingSession))
        assert charging_session.rfid_number == "BBBB0002"
        assert charging_session.rfid_assignment_id == assignment.id


def test_reimport_does_not_touch_invoiced_sessions() -> None:
    with create_database_session() as db:
        db.add(
            ChargingSession(
                hager_session_id="s1",
                station_id="WB-s1",
                start_time=SESSION_START_LOCAL,
                end_time=datetime(2026, 7, 15, 12, 26, 37),
                rfid_number=None,
                energy_total_kwh=5.0,
                energy_pv_kwh=0.0,
                invoiced=True,
                invoice_id=None,
                import_hash="x" * 64,
                source="json",
            )
        )
        db.commit()

        result = import_items_to_db(db, [hager_item("s1", "BBBB0002")])

        assert result["backfilled_rfid_numbers"] == 0
        assert db.scalar(select(ChargingSession)).rfid_number is None
