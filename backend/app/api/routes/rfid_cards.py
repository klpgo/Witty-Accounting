from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.charging_session import ChargingSession
from app.models.rfid_card import RFIDCard
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.schemas.rfid_card import (
    RFIDCardAssignmentCreate,
    RFIDCardAssignmentResponse,
    RFIDCardAssignmentUpdate,
    RFIDCardCreate,
    RFIDCardResponse,
    RFIDCardUpdate,
)
from app.models.user import User
from app.services.rfid_assignments import (
    RFIDAssignmentOverlapError,
    ensure_rfid_assignment_period_available,
)


router = APIRouter(
    prefix="/rfid-cards",
    tags=["rfid-cards"],
)


assignment_router = APIRouter(
    prefix="/rfid-card-assignments",
    tags=["rfid-card-assignments"],
)


def get_rfid_card_or_404(
    db: Session,
    card_id: int,
) -> RFIDCard:
    card = db.get(
        RFIDCard,
        card_id,
    )

    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"RFID-Karte {card_id} wurde "
                "nicht gefunden."
            ),
        )

    return card


def get_rfid_assignment_or_404(
    db: Session,
    assignment_id: int,
) -> RFIDCardAssignment:
    assignment = db.get(
        RFIDCardAssignment,
        assignment_id,
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"RFID-Zuordnung {assignment_id} "
                "wurde nicht gefunden."
            ),
        )

    return assignment


def ensure_rfid_number_available(
    db: Session,
    *,
    rfid_number: str,
    current_card_id: int | None = None,
) -> None:
    statement = select(RFIDCard.id).where(
        func.lower(RFIDCard.rfid_number)
        == rfid_number.lower()
    )

    if current_card_id is not None:
        statement = statement.where(
            RFIDCard.id != current_card_id
        )

    existing_card_id = db.scalar(statement)

    if existing_card_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese RFID-Nummer wird "
                "bereits verwendet."
            ),
        )


@router.get(
    "",
    response_model=list[RFIDCardResponse],
    dependencies=[Depends(require_admin)],
)
def list_rfid_cards(
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> list[RFIDCard]:
    return list(
        db.scalars(
            select(RFIDCard).order_by(
                RFIDCard.rfid_number,
                RFIDCard.id,
            )
        ).all()
    )


@router.post(
    "",
    response_model=RFIDCardResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_rfid_card(
    payload: RFIDCardCreate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> RFIDCard:
    ensure_rfid_number_available(
        db,
        rfid_number=payload.rfid_number,
    )

    card = RFIDCard(
        rfid_number=payload.rfid_number,
        description=payload.description,
        active=payload.active,
    )

    db.add(card)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese RFID-Nummer wird "
                "bereits verwendet."
            ),
        ) from exc

    db.refresh(card)

    return card


@router.patch(
    "/{card_id}",
    response_model=RFIDCardResponse,
    dependencies=[Depends(require_admin)],
)
def update_rfid_card(
    card_id: int,
    payload: RFIDCardUpdate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> RFIDCard:
    card = get_rfid_card_or_404(
        db,
        card_id,
    )

    if (
        "rfid_number"
        in payload.model_fields_set
    ):
        assert payload.rfid_number is not None

        ensure_rfid_number_available(
            db,
            rfid_number=payload.rfid_number,
            current_card_id=card.id,
        )

        card.rfid_number = payload.rfid_number

    if (
        "description"
        in payload.model_fields_set
    ):
        card.description = payload.description

    if "active" in payload.model_fields_set:
        assert payload.active is not None
        card.active = payload.active

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese RFID-Nummer wird "
                "bereits verwendet."
            ),
        ) from exc

    db.refresh(card)

    return card


@router.post(
    "/{card_id}/assignments",
    response_model=RFIDCardAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_rfid_card_assignment(
    card_id: int,
    payload: RFIDCardAssignmentCreate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> RFIDCardAssignment:
    get_rfid_card_or_404(
        db,
        card_id,
    )

    user = db.get(
        User,
        payload.user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Benutzer {payload.user_id} "
                "wurde nicht gefunden."
            ),
        )

    try:
        ensure_rfid_assignment_period_available(
            db,
            rfid_card_id=card_id,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
        )
    except RFIDAssignmentOverlapError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    assignment = RFIDCardAssignment(
        rfid_card_id=card_id,
        user_id=user.id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        note=payload.note,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


@router.get(
    "/{card_id}/assignments",
    response_model=list[
        RFIDCardAssignmentResponse
    ],
    dependencies=[Depends(require_admin)],
)
def list_rfid_card_assignments(
    card_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> list[RFIDCardAssignment]:
    get_rfid_card_or_404(
        db,
        card_id,
    )

    return list(
        db.scalars(
            select(RFIDCardAssignment)
            .where(
                RFIDCardAssignment.rfid_card_id
                == card_id
            )
            .order_by(
                RFIDCardAssignment.valid_from,
                RFIDCardAssignment.id,
            )
        ).all()
    )


@assignment_router.patch(
    "/{assignment_id}",
    response_model=RFIDCardAssignmentResponse,
    dependencies=[Depends(require_admin)],
)
def update_rfid_card_assignment(
    assignment_id: int,
    payload: RFIDCardAssignmentUpdate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> RFIDCardAssignment:
    assignment = get_rfid_assignment_or_404(
        db,
        assignment_id,
    )

    fields = payload.model_fields_set

    candidate_user_id = assignment.user_id
    candidate_valid_from = assignment.valid_from
    candidate_valid_to = assignment.valid_to

    if "user_id" in fields:
        assert payload.user_id is not None

        user = db.get(
            User,
            payload.user_id,
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Benutzer {payload.user_id} "
                    "wurde nicht gefunden."
                ),
            )

        candidate_user_id = payload.user_id

    if "valid_from" in fields:
        assert payload.valid_from is not None
        candidate_valid_from = payload.valid_from

    if "valid_to" in fields:
        candidate_valid_to = payload.valid_to

    if (
        candidate_valid_to is not None
        and candidate_valid_to
        <= candidate_valid_from
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=(
                "Das Ende der Zuordnung muss "
                "nach ihrem Beginn liegen."
            ),
        )

    session_count, first_start, last_start = (
        db.execute(
            select(
                func.count(ChargingSession.id),
                func.min(
                    ChargingSession.start_time
                ),
                func.max(
                    ChargingSession.start_time
                ),
            ).where(
                ChargingSession.rfid_assignment_id
                == assignment.id
            )
        ).one()
    )

    if session_count:
        if (
            candidate_user_id
            != assignment.user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Der Benutzer einer bereits "
                    "verwendeten RFID-Zuordnung "
                    "darf nicht geändert werden."
                ),
            )

        if (
            candidate_valid_from
            != assignment.valid_from
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Der Beginn einer bereits "
                    "verwendeten RFID-Zuordnung "
                    "darf nicht geändert werden."
                ),
            )

        if (
            first_start is not None
            and first_start
            < candidate_valid_from
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Der neue Zeitraum enthält "
                    "nicht mehr alle zugehörigen "
                    "Ladevorgänge."
                ),
            )

        if (
            last_start is not None
            and candidate_valid_to is not None
            and last_start
            >= candidate_valid_to
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Der neue Zeitraum enthält "
                    "nicht mehr alle zugehörigen "
                    "Ladevorgänge."
                ),
            )

    try:
        ensure_rfid_assignment_period_available(
            db,
            rfid_card_id=assignment.rfid_card_id,
            valid_from=candidate_valid_from,
            valid_to=candidate_valid_to,
            current_assignment_id=assignment.id,
        )
    except RFIDAssignmentOverlapError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    assignment.user_id = candidate_user_id
    assignment.valid_from = candidate_valid_from
    assignment.valid_to = candidate_valid_to

    if "note" in fields:
        assignment.note = payload.note

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Die RFID-Zuordnung konnte wegen "
                "eines Datenkonflikts nicht "
                "geändert werden."
            ),
        ) from exc

    db.refresh(assignment)

    return assignment
