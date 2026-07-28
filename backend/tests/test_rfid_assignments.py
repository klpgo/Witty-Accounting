from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.services.rfid_assignments import (
    RFIDAssignmentOverlapError,
    resolve_rfid_assignment,
)


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


def create_user(
    db: Session,
    *,
    email: str,
    first_name: str,
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
        is_admin=False,
    )

    db.add(user)
    db.flush()

    return user


def create_card(
    db: Session,
    *,
    user: User,
    active: bool = True,
) -> RFIDCard:
    card = RFIDCard(
        user_id=user.id,
        rfid_number="TEST-CARD",
        description="Testkarte",
        active=active,
    )

    db.add(card)
    db.flush()

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
        rfid_card_id=card.id,
        user_id=user.id,
        valid_from=valid_from,
        valid_to=valid_to,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


def test_resolves_assignment_for_timestamp(
    database_session: Session,
) -> None:
    user = create_user(
        database_session,
        email="first@example.com",
        first_name="First",
    )

    card = create_card(
        database_session,
        user=user,
    )

    assignment = create_assignment(
        database_session,
        card=card,
        user=user,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
    )

    result = resolve_rfid_assignment(
        database_session,
        rfid_number="TEST-CARD",
        at=datetime(
            2026,
            7,
            15,
            10,
            0,
        ),
    )

    assert result is not None
    assert result.id == assignment.id
    assert result.user_id == user.id


def test_uses_half_open_assignment_periods(
    database_session: Session,
) -> None:
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
    )

    change_time = datetime(
        2026,
        8,
        1,
        0,
        0,
    )

    first_assignment = create_assignment(
        database_session,
        card=card,
        user=first_user,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
        valid_to=change_time,
    )

    second_assignment = create_assignment(
        database_session,
        card=card,
        user=second_user,
        valid_from=change_time,
    )

    before_change = resolve_rfid_assignment(
        database_session,
        rfid_number="TEST-CARD",
        at=datetime(
            2026,
            7,
            31,
            23,
            59,
            59,
        ),
    )

    at_change = resolve_rfid_assignment(
        database_session,
        rfid_number="TEST-CARD",
        at=change_time,
    )

    assert before_change is not None
    assert before_change.id == first_assignment.id

    assert at_change is not None
    assert at_change.id == second_assignment.id


def test_returns_none_before_assignment_starts(
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
    )

    create_assignment(
        database_session,
        card=card,
        user=user,
        valid_from=datetime(
            2026,
            8,
            1,
        ),
    )

    result = resolve_rfid_assignment(
        database_session,
        rfid_number="TEST-CARD",
        at=datetime(
            2026,
            7,
            31,
            23,
            59,
            59,
        ),
    )

    assert result is None


def test_returns_none_for_inactive_card(
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
        active=False,
    )

    create_assignment(
        database_session,
        card=card,
        user=user,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
    )

    result = resolve_rfid_assignment(
        database_session,
        rfid_number="TEST-CARD",
        at=datetime(
            2026,
            7,
            15,
        ),
    )

    assert result is None


def test_rejects_overlapping_assignments(
    database_session: Session,
) -> None:
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
    )

    create_assignment(
        database_session,
        card=card,
        user=first_user,
        valid_from=datetime(
            2026,
            1,
            1,
        ),
    )

    create_assignment(
        database_session,
        card=card,
        user=second_user,
        valid_from=datetime(
            2026,
            6,
            1,
        ),
    )

    with pytest.raises(
        RFIDAssignmentOverlapError
    ):
        resolve_rfid_assignment(
            database_session,
            rfid_number="TEST-CARD",
            at=datetime(
                2026,
                7,
                15,
            ),
        )
