from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import tenant_session_provider
from app.tenancy.context import TenantContext
from app.tenancy.registry import (
    TenantInactiveError,
    TenantNotFoundError,
    tenant_registry,
)


def get_tenant_context(
    request: Request,
) -> TenantContext:
    hostname = request.url.hostname or ""

    try:
        tenant = tenant_registry.resolve(hostname)
    except TenantInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieser Mandant ist gesperrt.",
        ) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unbekannter Mandant.",
        ) from exc

    request.state.tenant = tenant
    return tenant


def get_db(
    tenant: TenantContext = Depends(
        get_tenant_context
    ),
) -> Generator[Session, None, None]:
    db = tenant_session_provider.create_session(
        tenant
    )

    try:
        yield db
    finally:
        db.close()
