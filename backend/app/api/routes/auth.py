from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import (
    authenticate_user,
    create_access_token,
)
from app.schemas.auth import Token


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/token",
    response_model=Token,
)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Token:
    user = authenticate_user(
        db=db,
        email=form_data.username,
        password=form_data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-Mail-Adresse oder Passwort ist falsch.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return Token(
        access_token=create_access_token(user),
    )
