from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.user import User
from app.schemas.retention import (
    RetentionDueResponse,
    RetentionOverviewResponse,
    RetentionPurgeRequest,
    RetentionPurgeResponse,
    RetentionSettingsUpdate,
)
from app.services.invoice_retention import (
    InvoiceRetentionError,
    RetentionPurgeBlockedError,
    build_overview,
    oldest_purgeable_year,
    purge_year,
    set_retention_years,
)


router = APIRouter(
    prefix="/retention",
    tags=["retention"],
)


@router.get(
    "",
    response_model=RetentionOverviewResponse,
    dependencies=[Depends(require_admin)],
)
def read_retention_overview(
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    return build_overview(db)


@router.get(
    "/due",
    response_model=RetentionDueResponse,
    dependencies=[Depends(require_admin)],
)
def read_retention_due(
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    return {"year": oldest_purgeable_year(db)}


@router.patch(
    "/settings",
    response_model=RetentionOverviewResponse,
    dependencies=[Depends(require_admin)],
)
def update_retention_settings(
    payload: RetentionSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    try:
        set_retention_years(db, payload.retention_years)
    except InvoiceRetentionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return build_overview(db)


@router.post(
    "/years/{year}/purge",
    response_model=RetentionPurgeResponse,
)
def purge_retention_year(
    year: int,
    payload: RetentionPurgeRequest,
    current_admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Löscht Rechnungen, Stornos, PDFs und Abrechnungsdaten eines Jahres,
    dessen Aufbewahrungsfrist abgelaufen ist. Nicht umkehrbar.
    """
    try:
        result = purge_year(
            db,
            year=year,
            confirm_year=payload.confirm_year,
            purged_by=(
                f"{current_admin.first_name} {current_admin.last_name} "
                f"<{current_admin.email}>"
            ),
        )
    except RetentionPurgeBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvoiceRetentionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return asdict(result)
