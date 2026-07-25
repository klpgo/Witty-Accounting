from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse

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

from app.services.invoice_archive import (
    InvoiceArchiveError,
    InvoiceArchiveMetadataError,
    InvoiceArchiveNotFoundError,
    InvoicePdfIntegrityError,
    archive_invoice_pdf,
    get_archived_invoice_pdf,
)

from app.services.invoice_pdf import (
    InvoiceNotFinalizedError,
    InvoicePdfError,
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
        invoice = finalize_invoice(
            db,
            invoice_id=invoice_id,
            issue_date=payload.issue_date,
            due_date=payload.due_date,
        )

        archive_invoice_pdf(
            db,
            invoice_id=invoice.id,
        )

        db.refresh(invoice)

        return invoice

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

    except (
        InvoiceArchiveError,
        InvoicePdfError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Die Rechnung wurde finalisiert, "
                "aber die PDF-Archivierung ist "
                f"fehlgeschlagen: {exc}"
            ),
        ) from exc

@router.post(
    "/{invoice_id}/archive",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_admin)],
)
def archive_invoice(
    invoice_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    try:
        archive_invoice_pdf(
            db,
            invoice_id=invoice_id,
        )

    except InvoiceArchiveNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvoiceNotFinalizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except (
        InvoiceArchiveMetadataError,
        InvoicePdfIntegrityError,
        InvoiceArchiveError,
        InvoicePdfError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

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


@router.get(
    "/{invoice_id}/pdf",
    response_class=FileResponse,
    dependencies=[Depends(require_admin)],
)
def download_invoice_pdf(
    invoice_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> FileResponse:
    try:
        archived_pdf = get_archived_invoice_pdf(
            db,
            invoice_id=invoice_id,
        )

    except InvoiceArchiveNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvoiceArchiveMetadataError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Für diese Rechnung wurde noch "
                "keine PDF archiviert."
            ),
        ) from exc

    except InvoicePdfIntegrityError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=archived_pdf.absolute_path,
        media_type="application/pdf",
        filename=archived_pdf.absolute_path.name,
    )


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
