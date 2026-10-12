import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.responses import FileResponse

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.api.dependencies import get_db
from app.auth import (
    get_current_user,
    require_admin,
)
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.models.user import User
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.schemas.invoice import (
    InvoiceDraftCreate,
    InvoiceFinalizeRequest,
    InvoiceResponse,
    InvoiceCancellationCreate,
    InvoiceCancellationFinalize,
)

from app.schemas.invoice import (
    InvoiceCancellationCreate,
    InvoiceCancellationFinalize,
    InvoiceDraftCreate,
    InvoiceEmailResponse,
    InvoiceFinalizeRequest,
    InvoiceInquiryResponse,
    InvoiceResponse,
)
from app.schemas.invoice_export import (
    InvoiceExportResponse,
)

from app.services.invoice_cancellation import (
    InvoiceAlreadyCancelledError,
    InvoiceCancellationError,
    InvoiceCancellationNotFoundError,
    InvoiceCancellationStateError,
    create_cancellation_draft,
    finalize_cancellation,
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
    InvoiceDraftError,
    InvoiceItemStateError,
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
    build_invoice_pdf,
)
from app.services.auto_billing import (
    InquiryNotFoundError,
    InquiryStateError,
    request_review_hold,
)
from app.services.billing_email import notification_address

from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    InvoiceEmailNotFoundError,
    InvoiceEmailRecipientError,
    InvoiceEmailStateError,
    send_invoice_email,
)
from app.services.invoice_export import (
    InvoiceExportAlreadyExistsError,
    InvoiceExportConfigurationError,
    InvoiceExportConnectionError,
    InvoiceExportNotFoundError,
    InvoiceExportStateError,
    export_invoice_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/invoices",
    tags=["invoices"],
)


def customer_visibility():
    """
    Kunden sehen ihre finalisierten Rechnungen und Entwürfe der
    automatischen Abrechnung, die ihnen zur Prüfung gesendet wurden.
    Manuell erstellte Entwürfe bleiben verborgen.
    """
    return or_(
        Invoice.status == "finalized",
        and_(
            Invoice.status == "draft",
            Invoice.review_status.is_not(None),
        ),
    )


def to_invoice_response(
    db: Session,
    invoice: Invoice,
    current_user: User,
) -> InvoiceResponse:
    response = InvoiceResponse.model_validate(invoice)
    updates: dict[str, object] = {}

    if invoice.status == "draft" and invoice.review_status is not None:
        updates["review_contact_email"] = notification_address(db)

    if not current_user.is_admin:
        # technische Fehlermeldungen nur für Administratoren
        updates["notification_error"] = None

    return response.model_copy(update=updates) if updates else response


def get_readable_invoice_or_404(
    db: Session,
    *,
    invoice_id: int,
    current_user: User,
    include_items: bool = False,
) -> Invoice:
    statement = select(Invoice).where(
        Invoice.id == invoice_id
    )

    if include_items:
        statement = statement.options(
            selectinload(Invoice.items)
        )

    if not current_user.is_admin:
        statement = statement.where(
            Invoice.user_id == current_user.id,
            customer_visibility(),
        )

    invoice = db.scalar(statement)

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Invoice {invoice_id} was not found."
            ),
        )

    return invoice


@router.get(
    "",
    response_model=list[InvoiceResponse],
)
def list_invoices(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> list[InvoiceResponse]:
    statement = (
        select(Invoice)
        .options(
            selectinload(Invoice.items)
        )
        # Neueste oben: Entwürfe (noch ohne Rechnungsdatum) zuerst,
        # dann nach Rechnungsdatum absteigend. "IS NULL DESC" statt
        # NULLS FIRST, weil MariaDB das nicht unterstützt.
        .order_by(
            Invoice.issue_date.is_(None).desc(),
            Invoice.issue_date.desc(),
            Invoice.created_at.desc(),
            Invoice.id.desc(),
        )
    )

    if not current_user.is_admin:
        statement = statement.where(
            Invoice.user_id == current_user.id,
            customer_visibility(),
        )

    return [
        to_invoice_response(db, invoice, current_user)
        for invoice in db.scalars(statement).all()
    ]


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
            prorate_base_fee=payload.prorate_base_fee,
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
        InvoiceDraftError,
        NoBillableSessionsError,
        MissingEnergyPriceError,
        InvalidChargingSessionError,
        InvoiceItemStateError,
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
        logger.error(
            "Invoice %s finalized, PDF archiving failed (%s): %s",
            invoice_id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                f"The invoice was finalized, but PDF archiving failed: {exc}"
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
        logger.error(
            "PDF archiving for invoice %s failed (%s): %s",
            invoice_id,
            type(exc).__name__,
            exc,
        )
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
                f"Invoice {invoice_id} was not found."
            ),
        )

    return invoice


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_invoice_draft(
    invoice_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    invoice = db.get(
        Invoice,
        invoice_id,
    )

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Invoice {invoice_id} was not found."
            ),
        )

    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a draft can be deleted."
            ),
        )

    try:
        base_fee_charges = list(
            db.scalars(
                select(MonthlyBaseFeeCharge)
                .where(
                    MonthlyBaseFeeCharge.invoice_id
                    == invoice.id
                )
                .with_for_update()
            ).all()
        )

        for base_fee_charge in base_fee_charges:
            base_fee_charge.invoice_id = None
            base_fee_charge.invoiced = False

        # Der Foreign Key der Grundgebühr verwendet
        # ON DELETE RESTRICT. Daher zuerst freigeben.
        db.flush()

        db.delete(invoice)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )


@router.get(
    "/{invoice_id}/pdf",
    response_class=FileResponse,
)
def download_invoice_pdf(
    invoice_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> FileResponse:
    get_readable_invoice_or_404(
        db,
        invoice_id=invoice_id,
        current_user=current_user,
    )
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
                "No PDF has been archived for this invoice yet."
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
    "/{invoice_id}/draft-pdf",
)
def download_invoice_draft_pdf(
    invoice_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    """
    Ansicht eines Rechnungsentwurfs als PDF (Wasserzeichen "ENTWURF", ohne
    Rechnungsnummer und Girocode). Wird bei jedem Abruf neu erzeugt und
    nicht archiviert.
    """
    invoice = get_readable_invoice_or_404(
        db,
        invoice_id=invoice_id,
        current_user=current_user,
        include_items=True,
    )

    if (
        invoice.status != "draft"
        or invoice.document_type != "invoice"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only invoice drafts can be shown as a draft PDF.",
        )

    global_settings = db.get(GlobalSettings, 1)

    try:
        pdf_bytes = build_invoice_pdf(
            invoice,
            draft=True,
            payment_term_days=(
                global_settings.invoice_payment_term_days
                if global_settings is not None
                else None
            ),
        )
    except InvoicePdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="rechnungsentwurf-{invoice.id}.pdf"'
            ),
        },
    )


@router.post(
    "/{invoice_id}/inquiry",
    response_model=InvoiceInquiryResponse,
)
def create_invoice_inquiry(
    invoice_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> InvoiceInquiryResponse:
    """
    "Nachfrage zum Rechnungsentwurf" durch den Kunden: der Entwurf wird
    zurückgestellt und nicht automatisch finalisiert; der
    Rechnungssteller wird per E-Mail benachrichtigt.
    """
    try:
        invoice, contact_email = request_review_hold(
            db,
            invoice_id=invoice_id,
            user=current_user,
        )
    except InquiryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InquiryStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    invoice = get_readable_invoice_or_404(
        db,
        invoice_id=invoice.id,
        current_user=current_user,
        include_items=True,
    )

    return InvoiceInquiryResponse(
        invoice=to_invoice_response(db, invoice, current_user),
        contact_email=contact_email,
    )


@router.post(
    "/{invoice_id}/cancellations",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_invoice_cancellation(
    invoice_id: int,
    payload: InvoiceCancellationCreate,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    try:
        return create_cancellation_draft(
            db,
            original_invoice_id=invoice_id,
            reason=payload.reason,
        )

    except InvoiceCancellationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        InvoiceAlreadyCancelledError,
        InvoiceCancellationStateError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except InvoiceCancellationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{cancellation_id}/cancellation/finalize",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_admin)],
)
def finalize_invoice_cancellation(
    cancellation_id: int,
    payload: InvoiceCancellationFinalize,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Invoice:
    try:
        cancellation = finalize_cancellation(
            db,
            cancellation_id=cancellation_id,
            issue_date=payload.issue_date,
        )

        archive_invoice_pdf(
            db,
            invoice_id=cancellation.id,
        )

        db.refresh(cancellation)

        return cancellation

    except InvoiceCancellationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvoiceCancellationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except (
        InvoiceArchiveError,
        InvoicePdfError,
    ) as exc:
        logger.error(
            "Cancellation %s finalized, PDF archiving failed (%s): %s",
            cancellation_id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                f"The cancellation was finalized, but PDF archiving failed: {exc}"
            ),
        ) from exc

    except InvoiceCancellationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc


@router.post(
    "/{invoice_id}/send-email",
    response_model=InvoiceEmailResponse,
    dependencies=[Depends(require_admin)],
)
def send_invoice_by_email(
    invoice_id: int,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> InvoiceEmailResponse:
    try:
        result = send_invoice_email(
            db,
            invoice_id=invoice_id,
        )

        return InvoiceEmailResponse(
            recipient_email=(
                result.recipient_email
            ),
            subject=result.subject,
        )

    except InvoiceEmailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        InvoiceEmailStateError,
        InvoiceEmailRecipientError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except InvoiceEmailConfigurationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

    except InvoiceEmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/{invoice_id}/export-sftp",
    response_model=InvoiceExportResponse,
)
def export_invoice_by_sftp(
    invoice_id: int,
    current_admin: Annotated[
        User,
        Depends(require_admin),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> InvoiceExportResponse:
    try:
        result = export_invoice_pdf(
            db,
            invoice_id=invoice_id,
            admin_user_id=current_admin.id,
        )
    except InvoiceExportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (
        InvoiceExportStateError,
        InvoiceExportAlreadyExistsError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvoiceExportConfigurationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(exc),
        ) from exc
    except InvoiceExportConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return InvoiceExportResponse(
        remote_path=result.remote_path,
        exported_at=result.exported_at,
    )


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
)
def get_invoice(
    invoice_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> InvoiceResponse:

    return to_invoice_response(
        db,
        get_readable_invoice_or_404(
            db,
            invoice_id=invoice_id,
            current_user=current_user,
            include_items=True,
        ),
        current_user,
    )
