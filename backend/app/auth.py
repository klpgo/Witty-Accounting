from app.config import settings

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    get_tenant_context,
)
from app.database import DEFAULT_TENANT
from app.models.user import User
from app.security import verify_password
from app.tenancy.context import TenantContext


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token",
)


def get_jwt_secret() -> str:
    secret = settings.jwt_secret_key.get_secret_value()

    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY ist kürzer als 32 Byte."
        )

    return secret


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    normalized_email = email.strip().lower()

    user = db.scalar(
        select(User).where(
            User.email == normalized_email
        )
    )

    if user is None or not user.active:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user


def create_access_token(
    user: User,
    *,
    tenant_id: int | None = None,
) -> str:
    if tenant_id is None:
        if settings.tenancy_enabled:
            raise RuntimeError(
                "Beim Erzeugen eines Tokens fehlt "
                "der Mandantenkontext."
            )

        tenant_id = DEFAULT_TENANT.id

    now = datetime.now(UTC)

    payload = {
        "sub": str(user.id),
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Anmeldedaten konnten nicht validiert werden.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def get_current_user(
    token: Annotated[
        str,
        Depends(oauth2_scheme),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    tenant: Annotated[
        TenantContext,
        Depends(get_tenant_context),
    ],
) -> User:
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
        )

        subject = payload.get("sub")
        token_tenant_id = payload.get(
            "tenant_id"
        )

        if subject is None:
            raise credentials_exception()

        user_id = int(subject)

        if token_tenant_id is None:
            if settings.tenancy_enabled:
                raise credentials_exception()

            token_tenant_id = tenant.id

        if int(token_tenant_id) != tenant.id:
            raise credentials_exception()

    except (
        InvalidTokenError,
        TypeError,
        ValueError,
    ) as exc:
        raise credentials_exception() from exc

    user = db.get(
        User,
        user_id,
    )

    if user is None or not user.active:
        raise credentials_exception()

    return user


def require_admin(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administratorrechte erforderlich.",
        )

    return current_user
