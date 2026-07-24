from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.api.dependencies import get_db
from app.auth import require_admin
from app.models.invoice import Invoice
from app.schemas.invoice import (
    InvoiceDraftCreate,
    InvoiceFinalizeRequest,
    InvoiceResponse,
)
from app.services.invoicing import (
    InvalidDueDateError,
    EmptyInvoiceError,
    InvalidChargingSessionError,
    InvalidServicePeriodError,
    InvoiceAlreadyFinalizedError,
    InvoiceNotFoundError,
    InvoiceSessionAlreadyInvoicedError,
    InvoiceUserNotFoundError,
    MissingEnergyPriceError,
    NoBillableSessionsError,
    create_invoice_draft,
    finalize_invoice,
)

router = APIRouter(
    prefix="/invoices",
    tags=["invoices"],
)


@router.get(
    "",
    response_model=list[InvoiceResponse],
    dependencies=[Depends(require_admin)],
)
def list_invoices(
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> list[Invoice]:
    return list(
        db.scalars(
            select(Invoice)
            .options(
                selectinload(Invoice.items)
            )
            .order_by(
                Invoice.created_at.desc(),
                Invoice.id.desc(),
            )
        ).all()
    )


@router.post(
    "/drafts",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_draft(
    payload: InvoiceDraftCreate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    try:
        return create_invoice_draft(
            db,
            user_id=payload.user_id,
            service_period_start=(
                payload.service_period_start
            ),
            service_period_end=(
                payload.service_period_end
            ),
        )

    except InvoiceUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidDueDateError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    except InvalidServicePeriodError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    except (
        NoBillableSessionsError,
        MissingEnergyPriceError,
        InvalidChargingSessionError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{invoice_id}/finalize",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_admin)],
)
def finalize_draft(
    invoice_id: int,
    payload: InvoiceFinalizeRequest,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    try:
        return finalize_invoice(
            db,
            invoice_id=invoice_id,
            issue_date=payload.issue_date,
            due_date=payload.due_date,
        )

    except InvoiceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        InvoiceAlreadyFinalizedError,
        EmptyInvoiceError,
        InvoiceSessionAlreadyInvoicedError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_admin)],
)
def get_invoice(
    invoice_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.items)
        )
        .where(Invoice.id == invoice_id)
    )

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Rechnung {invoice_id} "
                "wurde nicht gefunden."
            ),
        )

    return invoice
