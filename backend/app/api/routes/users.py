from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import (
    get_current_user,
    require_admin,
)
from app.models.user import User
from app.schemas.user import (
    UserAdminUpdate,
    UserPasswordChange,
    UserPasswordReset,
    UserProfileUpdate,
    UserResponse,
)
from app.security import (
    hash_password,
    verify_password,
)

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def ensure_email_available(
    db: Session,
    *,
    email: str,
    current_user_id: int,
) -> None:
    existing_user = db.scalar(
        select(User).where(
            func.lower(User.email)
            == email.lower(),
            User.id != current_user_id,
        )
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese E-Mail-Adresse wird "
                "bereits verwendet."
            ),
        )


def get_user_or_404(
    db: Session,
    user_id: int,
) -> User:
    user = db.get(
        User,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Benutzer {user_id} wurde "
                "nicht gefunden."
            ),
        )

    return user


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_own_profile(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
)
def update_own_profile(
    payload: UserProfileUpdate,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    if "email" in payload.model_fields_set:
        assert payload.email is not None

        ensure_email_available(
            db,
            email=payload.email,
            current_user_id=current_user.id,
        )

        current_user.email = payload.email

    if "first_name" in payload.model_fields_set:
        assert payload.first_name is not None
        current_user.first_name = (
            payload.first_name
        )

    if "last_name" in payload.model_fields_set:
        assert payload.last_name is not None
        current_user.last_name = (
            payload.last_name
        )

    if "address" in payload.model_fields_set:
        current_user.address = payload.address

    if (
        "invoice_delivery_email"
        in payload.model_fields_set
    ):
        assert (
            payload.invoice_delivery_email
            is not None
        )
        user.invoice_delivery_email = (
            payload.invoice_delivery_email
        )

    if (
        "invoice_delivery_post"
        in payload.model_fields_set
    ):
        assert (
            payload.invoice_delivery_post
            is not None
        )
        user.invoice_delivery_post = (
            payload.invoice_delivery_post
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese E-Mail-Adresse wird "
                "bereits verwendet."
            ),
        ) from exc

    db.refresh(current_user)

    return current_user


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_own_password(
    payload: UserPasswordChange,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    if not verify_password(
        payload.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Das aktuelle Passwort ist "
                "nicht korrekt."
            ),
        )

    current_user.password_hash = hash_password(
        payload.new_password
    )

    db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )


@router.get(
    "",
    response_model=list[UserResponse],
    dependencies=[Depends(require_admin)],
)
def list_users(
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> list[User]:
    return list(
        db.scalars(
            select(User).order_by(
                User.last_name,
                User.first_name,
                User.id,
            )
        ).all()
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_admin)],
)
def get_user(
    user_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    return get_user_or_404(
        db,
        user_id,
    )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_admin)],
)
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    user = get_user_or_404(
        db,
        user_id,
    )

    if "email" in payload.model_fields_set:
        assert payload.email is not None

        ensure_email_available(
            db,
            email=payload.email,
            current_user_id=user.id,
        )

        user.email = payload.email

    if "first_name" in payload.model_fields_set:
        assert payload.first_name is not None
        user.first_name = payload.first_name

    if "last_name" in payload.model_fields_set:
        assert payload.last_name is not None
        user.last_name = payload.last_name

    if "address" in payload.model_fields_set:
        user.address = payload.address

    if (
        "invoice_delivery_email"
        in payload.model_fields_set
    ):
        assert (
            payload.invoice_delivery_email
            is not None
        )
        user.invoice_delivery_email = (
            payload.invoice_delivery_email
        )

    if (
        "invoice_delivery_post"
        in payload.model_fields_set
    ):
        assert (
            payload.invoice_delivery_post
            is not None
        )
        user.invoice_delivery_post = (
            payload.invoice_delivery_post
        )

    if "active" in payload.model_fields_set:
        assert payload.active is not None
        user.active = payload.active

    if "is_admin" in payload.model_fields_set:
        assert payload.is_admin is not None
        user.is_admin = payload.is_admin

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diese E-Mail-Adresse wird "
                "bereits verwendet."
            ),
        ) from exc

    db.refresh(user)

    return user


@router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def reset_user_password(
    user_id: int,
    payload: UserPasswordReset,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    user = get_user_or_404(
        db,
        user_id,
    )

    user.password_hash = hash_password(
        payload.new_password
    )

    db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
