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
    get_current_user,
)
from app.models.user import User
from app.models.global_settings import GlobalSettings

from app.schemas.auth import (
    AuthenticatedUserResponse,
    Token,
)

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

    global_settings = db.get(
        GlobalSettings,
        1,
    )

    maintenance_mode = (
        global_settings is not None
        and global_settings.maintenance_mode
    )

    if maintenance_mode and not user.is_admin:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Der Wartungsmodus ist aktiv. "
                "Die Anmeldung ist derzeit nur für "
                "Administratoren möglich."
            ),
        )

    return Token(
        access_token=create_access_token(user),
    )


@router.get(
    "/me",
    response_model=AuthenticatedUserResponse,
)
def get_authenticated_user(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse.model_validate(
        current_user
    )
