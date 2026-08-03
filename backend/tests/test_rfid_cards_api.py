from collections.abc import Generator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import create_access_token
from app.database import Base
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User


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
    email: str,
    first_name: str,
    is_admin: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash="not-used",
        salutation=None,
        first_name=first_name,
        last_name="Test",
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


def authorization_header(
    user: User,
) -> dict[str, str]:
    token = create_access_token(user)

    return {
        "Authorization": f"Bearer {token}",
    }


def create_card(
    db: Session,
    *,
    user: User,
    rfid_number: str,
) -> RFIDCard:
    card = RFIDCard(
        rfid_number=rfid_number,
        description=None,
        active=True,
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    return card


def create_assignment(
    db: Session,
    *,
    card: RFIDCard,
    user: User,
    valid_from: datetime,
    valid_to: datetime | None = None,
) -> RFIDCardAssignment:
    assignment = RFIDCardAssignment(
        rfid_card=card,
        user=user,
        valid_from=valid_from,
        valid_to=valid_to,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


def create_charging_session(
    db: Session,
    *,
    card: RFIDCard,
    assignment: RFIDCardAssignment,
    start_time: datetime,
    import_hash: str,
) -> ChargingSession:
    session = ChargingSession(
        hager_session_id=None,
        station_id="WB-TEST",
        start_time=start_time,
        end_time=start_time + timedelta(hours=1),
        rfid_card=card,
        rfid_assignment=assignment,
        energy_total_kwh=10.0,
        energy_pv_kwh=4.0,
        import_hash=import_hash,
        source="xlsx",
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def test_list_rfid_cards_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/rfid-cards")

    assert response.status_code == 401


def test_list_rfid_cards_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
    )

    response = client.get(
        "/api/rfid-cards",
        headers=authorization_header(user),
    )

    assert response.status_code == 403


def test_admin_lists_rfid_cards(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    create_card(
        database_session,
        user=admin,
        rfid_number="ZZZ999",
    )

    create_card(
        database_session,
        user=admin,
        rfid_number="AAA111",
    )

    response = client.get(
        "/api/rfid-cards",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200

    body = response.json()

    assert [
        card["rfid_number"]
        for card in body
    ] == [
        "AAA111",
        "ZZZ999",
    ]

    assert "user_id" not in body[0]


def test_admin_lists_assignment_history(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    first_user = create_user(
        database_session,
        email="first@example.com",
        first_name="First",
    )

    second_user = create_user(
        database_session,
        email="second@example.com",
        first_name="Second",
    )

    card = create_card(
        database_session,
        user=first_user,
        rfid_number="HISTORY1",
    )

    change_time = datetime(
        2026,
        8,
        1,
    )

    database_session.add_all(
        [
            RFIDCardAssignment(
                rfid_card_id=card.id,
                user_id=first_user.id,
                valid_from=datetime(
                    2026,
                    1,
                    1,
                ),
                valid_to=change_time,
            ),
            RFIDCardAssignment(
                rfid_card_id=card.id,
                user_id=second_user.id,
                valid_from=change_time,
                valid_to=None,
            ),
        ]
    )

    database_session.commit()

    response = client.get(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(admin),
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 2
    assert body[0]["user_id"] == first_user.id
    assert body[1]["user_id"] == second_user.id
    assert body[0]["valid_to"] is not None
    assert body[1]["valid_to"] is None


def test_assignment_history_returns_not_found(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    response = client.get(
        "/api/rfid-cards/999999/assignments",
        headers=authorization_header(admin),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "RFID-Karte 999999 wurde nicht "
            "gefunden."
        ),
    }


def test_admin_creates_rfid_card(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    response = client.post(
        "/api/rfid-cards",
        headers=authorization_header(admin),
        json={
            "rfid_number": " abc123 ",
            "description": " Hauptkarte ",
            "active": True,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["rfid_number"] == "ABC123"
    assert body["description"] == "Hauptkarte"
    assert body["active"] is True
    assert "user_id" not in body

    card = database_session.get(
        RFIDCard,
        body["id"],
    )

    assert card is not None
    assert card.rfid_number == "ABC123"
    assert card.assignments == []


def test_create_rfid_card_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
    )

    response = client.post(
        "/api/rfid-cards",
        headers=authorization_header(user),
        json={
            "rfid_number": "ABC123",
        },
    )

    assert response.status_code == 403


def test_create_rfid_card_rejects_duplicate_number(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    create_card(
        database_session,
        user=admin,
        rfid_number="ABC123",
    )

    response = client.post(
        "/api/rfid-cards",
        headers=authorization_header(admin),
        json={
            "rfid_number": "abc123",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Diese RFID-Nummer wird "
            "bereits verwendet."
        ),
    }


def test_admin_updates_rfid_card(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    card = create_card(
        database_session,
        user=admin,
        rfid_number="OLD123",
    )

    response = client.patch(
        f"/api/rfid-cards/{card.id}",
        headers=authorization_header(admin),
        json={
            "rfid_number": " new123 ",
            "description": " Ersatzkarte ",
            "active": False,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["rfid_number"] == "NEW123"
    assert body["description"] == "Ersatzkarte"
    assert body["active"] is False

    database_session.refresh(card)

    assert card.rfid_number == "NEW123"
    assert card.description == "Ersatzkarte"
    assert card.active is False


def test_admin_removes_rfid_description(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    card = RFIDCard(
        rfid_number="DESCRIPTION1",
        description="Alte Beschreibung",
        active=True,
    )

    database_session.add(card)
    database_session.commit()
    database_session.refresh(card)

    response = client.patch(
        f"/api/rfid-cards/{card.id}",
        headers=authorization_header(admin),
        json={
            "description": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_update_rfid_card_rejects_duplicate_number(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    first_card = create_card(
        database_session,
        user=admin,
        rfid_number="FIRST1",
    )

    second_card = create_card(
        database_session,
        user=admin,
        rfid_number="SECOND2",
    )

    response = client.patch(
        f"/api/rfid-cards/{second_card.id}",
        headers=authorization_header(admin),
        json={
            "rfid_number": "first1",
        },
    )

    assert response.status_code == 409

    database_session.refresh(second_card)

    assert second_card.rfid_number == "SECOND2"
    assert first_card.rfid_number == "FIRST1"


def test_update_rfid_card_returns_not_found(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    response = client.patch(
        "/api/rfid-cards/999999",
        headers=authorization_header(admin),
        json={
            "active": False,
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "RFID-Karte 999999 wurde nicht "
            "gefunden."
        ),
    }


def test_admin_creates_rfid_assignment(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
    )

    card = create_card(
        database_session,
        user=target,
        rfid_number="ASSIGN1",
    )

    response = client.post(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(admin),
        json={
            "user_id": target.id,
            "valid_from": (
                "2026-08-01T00:00:00"
            ),
            "valid_to": None,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["rfid_card_id"] == card.id
    assert body["user_id"] == target.id
    assert body["valid_from"].startswith(
        "2026-08-01T00:00:00"
    )
    assert body["valid_to"] is None


def test_create_assignment_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="Normal",
    )

    card = create_card(
        database_session,
        user=user,
        rfid_number="ASSIGN2",
    )

    response = client.post(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(user),
        json={
            "user_id": user.id,
            "valid_from": (
                "2026-08-01T00:00:00"
            ),
        },
    )

    assert response.status_code == 403


def test_create_assignment_rejects_overlap(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    target = create_user(
        database_session,
        email="target@example.com",
        first_name="Target",
    )

    card = create_card(
        database_session,
        user=target,
        rfid_number="OVERLAP1",
    )

    database_session.add(
        RFIDCardAssignment(
            rfid_card_id=card.id,
            user_id=target.id,
            valid_from=datetime(
                2026,
                1,
                1,
            ),
            valid_to=None,
        )
    )
    database_session.commit()

    response = client.post(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(admin),
        json={
            "user_id": target.id,
            "valid_from": (
                "2026-08-01T00:00:00"
            ),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Der Zuordnungszeitraum "
            "überschneidet sich mit einer "
            "bestehenden Zuordnung dieser "
            "RFID-Karte."
        ),
    }


def test_create_assignment_allows_adjacent_period(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    first_user = create_user(
        database_session,
        email="first@example.com",
        first_name="First",
    )

    second_user = create_user(
        database_session,
        email="second@example.com",
        first_name="Second",
    )

    card = create_card(
        database_session,
        user=first_user,
        rfid_number="ADJACENT1",
    )

    change_time = datetime(
        2026,
        8,
        1,
    )

    database_session.add(
        RFIDCardAssignment(
            rfid_card_id=card.id,
            user_id=first_user.id,
            valid_from=datetime(
                2026,
                1,
                1,
            ),
            valid_to=change_time,
        )
    )
    database_session.commit()

    response = client.post(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(admin),
        json={
            "user_id": second_user.id,
            "valid_from": (
                "2026-08-01T00:00:00"
            ),
            "valid_to": None,
        },
    )

    assert response.status_code == 201
    assert (
        response.json()["user_id"]
        == second_user.id
    )


def test_create_assignment_rejects_invalid_period(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    card = create_card(
        database_session,
        user=admin,
        rfid_number="PERIOD1",
    )

    response = client.post(
        f"/api/rfid-cards/{card.id}/assignments",
        headers=authorization_header(admin),
        json={
            "user_id": admin.id,
            "valid_from": (
                "2026-08-01T00:00:00"
            ),
            "valid_to": (
                "2026-07-31T00:00:00"
            ),
        },
    )

    assert response.status_code == 422


def test_admin_updates_unused_assignment(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    first_user = create_user(
        database_session,
        email="first@example.com",
        first_name="First",
    )
    second_user = create_user(
        database_session,
        email="second@example.com",
        first_name="Second",
    )
    card = create_card(
        database_session,
        user=first_user,
        rfid_number="PATCH1",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=first_user,
        valid_from=datetime(2026, 1, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "user_id": second_user.id,
            "valid_from": "2026-02-01T00:00:00",
            "valid_to": "2026-03-01T00:00:00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == second_user.id
    assert (
        body["valid_from"]
        == "2026-02-01T00:00:00"
    )
    assert (
        body["valid_to"]
        == "2026-03-01T00:00:00"
    )

    database_session.refresh(assignment)
    assert assignment.user_id == second_user.id
    assert assignment.valid_from == datetime(
        2026,
        2,
        1,
    )
    assert assignment.valid_to == datetime(
        2026,
        3,
        1,
    )


def test_admin_opens_assignment_period(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH2",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
        valid_to=datetime(2026, 2, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_to": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["valid_to"] is None

    database_session.refresh(assignment)
    assert assignment.valid_to is None


def test_update_assignment_requires_admin(
    client: TestClient,
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="user@example.com",
        first_name="User",
    )
    card = create_card(
        database_session,
        user=user,
        rfid_number="PATCH3",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=user,
        valid_from=datetime(2026, 1, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(user),
        json={
            "valid_to": "2026-02-01T00:00:00",
        },
    )

    assert response.status_code == 403


def test_update_assignment_returns_404(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )

    response = client.patch(
        "/api/rfid-card-assignments/999999",
        headers=authorization_header(admin),
        json={
            "valid_to": "2026-02-01T00:00:00",
        },
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == (
            "RFID-Zuordnung 999999 "
            "wurde nicht gefunden."
        )
    )


def test_update_assignment_returns_404_for_unknown_user(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH4",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "user_id": 999999,
        },
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Benutzer 999999 wurde nicht gefunden."
    )


def test_update_assignment_rejects_overlap(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH5",
    )
    first_assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
        valid_to=datetime(2026, 2, 1),
    )
    create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 2, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{first_assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_to": "2026-03-01T00:00:00",
        },
    )

    assert response.status_code == 409
    assert "überschneidet sich" in (
        response.json()["detail"]
    )


def test_update_assignment_rejects_invalid_period(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH6",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
        valid_to=datetime(2026, 2, 1),
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_from": "2026-03-01T00:00:00",
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == (
            "Das Ende der Zuordnung muss "
            "nach ihrem Beginn liegen."
        )
    )


def test_used_assignment_rejects_user_change(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    second_user = create_user(
        database_session,
        email="second@example.com",
        first_name="Second",
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH7",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
    )
    create_charging_session(
        database_session,
        card=card,
        assignment=assignment,
        start_time=datetime(2026, 6, 15, 10, 0),
        import_hash="a" * 64,
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "user_id": second_user.id,
        },
    )

    assert response.status_code == 409
    assert "Benutzer" in response.json()["detail"]
    assert "nicht geändert" in (
        response.json()["detail"]
    )


def test_used_assignment_rejects_start_change(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH8",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
    )
    create_charging_session(
        database_session,
        card=card,
        assignment=assignment,
        start_time=datetime(2026, 6, 15, 10, 0),
        import_hash="b" * 64,
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_from": "2026-02-01T00:00:00",
        },
    )

    assert response.status_code == 409
    assert "Beginn" in response.json()["detail"]
    assert "nicht geändert" in (
        response.json()["detail"]
    )


def test_used_assignment_rejects_end_excluding_session(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH9",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
    )
    session_start = datetime(
        2026,
        6,
        15,
        10,
        0,
    )
    create_charging_session(
        database_session,
        card=card,
        assignment=assignment,
        start_time=session_start,
        import_hash="c" * 64,
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_to": (
                "2026-06-15T10:00:00"
            ),
        },
    )

    assert response.status_code == 409
    assert "Ladevorgänge" in (
        response.json()["detail"]
    )


def test_used_assignment_allows_safe_end_change(
    client: TestClient,
    database_session: Session,
) -> None:
    admin = create_user(
        database_session,
        email="admin@example.com",
        first_name="Admin",
        is_admin=True,
    )
    card = create_card(
        database_session,
        user=admin,
        rfid_number="PATCH10",
    )
    assignment = create_assignment(
        database_session,
        card=card,
        user=admin,
        valid_from=datetime(2026, 1, 1),
    )
    create_charging_session(
        database_session,
        card=card,
        assignment=assignment,
        start_time=datetime(2026, 6, 15, 10, 0),
        import_hash="d" * 64,
    )

    response = client.patch(
        (
            "/api/rfid-card-assignments/"
            f"{assignment.id}"
        ),
        headers=authorization_header(admin),
        json={
            "valid_to": (
                "2026-06-16T00:00:00"
            ),
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["valid_to"]
        == "2026-06-16T00:00:00"
    )

    database_session.refresh(assignment)
    assert assignment.valid_to == datetime(
        2026,
        6,
        16,
    )
