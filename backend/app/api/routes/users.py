from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.user import User
from app.schemas.user import UserResponse


router = APIRouter(
    prefix="/users",
    tags=["users"],
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
