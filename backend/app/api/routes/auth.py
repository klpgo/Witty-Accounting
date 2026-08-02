import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
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
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    Token,
)
from app.services.password_policy import (
    PasswordPolicyError,
)
from app.services.password_reset import (
    InvalidPasswordResetTokenError,
    PasswordResetEmailError,
    issue_password_reset,
    reset_password_with_token,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

logger = logging.getLogger(__name__)

PASSWORD_RESET_REQUEST_MESSAGE = (
    "Falls ein aktives Benutzerkonto mit dieser "
    "E-Mail-Adresse existiert, wurde ein Link zum "
    "Zurücksetzen des Passworts versendet."
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


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> PasswordResetRequestResponse:
    user = db.scalar(
        select(User).where(
            func.lower(User.email) == payload.email
        )
    )

    if user is not None and user.active:
        try:
            issue_password_reset(
                db,
                user=user,
                purpose="password_reset",
            )
            db.commit()
        except PasswordResetEmailError:
            db.rollback()
            logger.exception(
                "Password-reset email delivery failed."
            )

    return PasswordResetRequestResponse(
        message=PASSWORD_RESET_REQUEST_MESSAGE,
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    try:
        reset_password_with_token(
            db,
            token=payload.token,
            new_password=payload.new_password,
        )
    except InvalidPasswordResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Der Link ist ungültig, abgelaufen "
                "oder wurde bereits verwendet."
            ),
        ) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(exc),
        ) from exc

    db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
