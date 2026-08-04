from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.invoice import Invoice, InvoiceItem
from app.utils.utc import utc_now


class InvoiceCancellationError(Exception):
    pass


class InvoiceCancellationNotFoundError(
    InvoiceCancellationError
):
    pass


class InvoiceCancellationStateError(
    InvoiceCancellationError
):
    pass


class InvoiceAlreadyCancelledError(
    InvoiceCancellationError
):
    pass


def create_cancellation_draft(
    db: Session,
    *,
    original_invoice_id: int,
    reason: str,
) -> Invoice:
    normalized_reason = reason.strip()

    if not normalized_reason:
        raise InvoiceCancellationError(
            "Ein Stornierungsgrund ist erforderlich."
        )

    original_invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.items)
        )
        .where(
            Invoice.id == original_invoice_id
        )
        .with_for_update()
    )

    if original_invoice is None:
        raise InvoiceCancellationNotFoundError(
            f"Rechnung {original_invoice_id} "
            "wurde nicht gefunden."
        )

    if original_invoice.document_type != "invoice":
        raise InvoiceCancellationStateError(
            "Nur eine normale Rechnung kann "
            "storniert werden."
        )

    if original_invoice.status != "finalized":
        raise InvoiceCancellationStateError(
            "Nur eine finalisierte Rechnung kann "
            "storniert werden."
        )

    existing_cancellation = db.scalar(
        select(Invoice.id).where(
            Invoice.original_invoice_id
            == original_invoice.id
        )
    )

    if existing_cancellation is not None:
        raise InvoiceAlreadyCancelledError(
            "Für diese Rechnung existiert bereits "
            "ein Storno."
        )

    cancellation = Invoice(
        invoice_number=None,
        document_type="cancellation",
        original_invoice_id=original_invoice.id,
        cancellation_reason=normalized_reason,
        cancelled_at=None,
        user_id=original_invoice.user_id,
        issuer_name=original_invoice.issuer_name,
        issuer_address=(
            original_invoice.issuer_address
        ),
        issuer_tax_number=(
            original_invoice.issuer_tax_number
        ),
        issuer_vat_id=(
            original_invoice.issuer_vat_id
        ),
        issuer_bank_name=(
            original_invoice.issuer_bank_name
        ),
        issuer_iban=original_invoice.issuer_iban,
        issuer_bic=original_invoice.issuer_bic,
        recipient_name=(
            original_invoice.recipient_name
        ),
        recipient_address=(
            original_invoice.recipient_address
        ),
        status="draft",
        issue_date=None,
        due_date=None,
        service_period_start=(
            original_invoice.service_period_start
        ),
        service_period_end=(
            original_invoice.service_period_end
        ),
        currency=original_invoice.currency,
        total_net=-original_invoice.total_net,
        vat_amount=-original_invoice.vat_amount,
        total_gross=-original_invoice.total_gross,
        finalized_at=None,
        pdf_storage_path=None,
        pdf_sha256=None,
        pdf_size_bytes=None,
        pdf_created_at=None,
    )

    for original_item in original_invoice.items:
        cancellation.items.append(
            InvoiceItem(
                item_type=original_item.item_type,
                monthly_base_fee_charge_id=(
                    original_item.monthly_base_fee_charge_id
                ),
                charging_session_id=None,
                reversed_invoice_item_id=original_item.id,
                rebills_invoice_item_id=None,
                position_number=original_item.position_number,
                description=(
                    "Storno zu "
                    f"{original_item.description}"
                ),
                session_start=original_item.session_start,
                session_end=original_item.session_end,
                station_id=original_item.station_id,
                energy_total_kwh=(
                    -original_item.energy_total_kwh
                    if original_item.energy_total_kwh
                    is not None
                    else None
                ),
                energy_grid_kwh=(
                    -original_item.energy_grid_kwh
                    if original_item.energy_grid_kwh
                    is not None
                    else None
                ),
                energy_pv_kwh=(
                    -original_item.energy_pv_kwh
                    if original_item.energy_pv_kwh
                    is not None
                    else None
                ),
                grid_price_net=(
                    original_item.grid_price_net
                ),
                pv_price_net=(
                    original_item.pv_price_net
                ),
                cost_grid_net=(
                    -original_item.cost_grid_net
                    if original_item.cost_grid_net
                    is not None
                    else None
                ),
                cost_pv_net=(
                    -original_item.cost_pv_net
                    if original_item.cost_pv_net
                    is not None
                    else None
                ),
                net_amount=(
                    -original_item.net_amount
                ),
                vat_rate=original_item.vat_rate,
                vat_amount=(
                    -original_item.vat_amount
                ),
                gross_amount=(
                    -original_item.gross_amount
                ),
            )
        )

    try:
        db.add(cancellation)
        db.commit()

        cancellation = db.scalar(
            select(Invoice)
            .options(
                selectinload(Invoice.items)
            )
            .where(Invoice.id == cancellation.id)
        )

        if cancellation is None:
            raise InvoiceCancellationError(
                "Der Storno-Entwurf konnte nicht "
                "geladen werden."
            )

        return cancellation

    except Exception:
        db.rollback()
        raise


def create_cancellation_number(
    db: Session,
    *,
    issue_date: date,
) -> str:
    prefix = f"ST-{issue_date.year}-"

    last_number = db.scalar(
        select(Invoice.invoice_number)
        .where(
            Invoice.document_type == "cancellation",
            Invoice.invoice_number.is_not(None),
            Invoice.invoice_number.like(
                f"{prefix}%"
            ),
        )
        .order_by(
            Invoice.invoice_number.desc()
        )
        .limit(1)
    )

    sequence_number = 1

    if last_number is not None:
        try:
            sequence_number = (
                int(last_number.rsplit("-", 1)[1])
                + 1
            )
        except (IndexError, ValueError) as exc:
            raise InvoiceCancellationError(
                "Die letzte Stornonummer besitzt "
                "ein ungültiges Format."
            ) from exc

    return f"{prefix}{sequence_number:06d}"


def finalize_cancellation(
    db: Session,
    *,
    cancellation_id: int,
    issue_date: date,
) -> Invoice:
    cancellation = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.items)
            .selectinload(
                InvoiceItem.reversed_invoice_item
            )
            .selectinload(
                InvoiceItem.charging_session
            ),
            selectinload(Invoice.items)
            .selectinload(
                InvoiceItem.reversed_invoice_item
            )
            .selectinload(
                InvoiceItem.monthly_base_fee_charge
            ),
            selectinload(
                Invoice.original_invoice
            ),
        )
        .where(
            Invoice.id == cancellation_id
        )
        .with_for_update()
    )

    if cancellation is None:
        raise InvoiceCancellationNotFoundError(
            f"Storno {cancellation_id} "
            "wurde nicht gefunden."
        )

    if cancellation.document_type != "cancellation":
        raise InvoiceCancellationStateError(
            "Nur ein Stornodokument kann über "
            "diese Funktion finalisiert werden."
        )

    if cancellation.status != "draft":
        raise InvoiceCancellationStateError(
            "Nur ein Storno-Entwurf kann "
            "finalisiert werden."
        )

    original_invoice = cancellation.original_invoice

    if original_invoice is None:
        raise InvoiceCancellationStateError(
            "Dem Storno ist keine "
            "Originalrechnung zugeordnet."
        )

    if original_invoice.status != "finalized":
        raise InvoiceCancellationStateError(
            "Die Originalrechnung ist nicht "
            "finalisiert."
        )

    if (
        original_invoice.issue_date is not None
        and issue_date < original_invoice.issue_date
    ):
        raise InvoiceCancellationStateError(
            "Das Stornodatum darf nicht vor "
            "dem Rechnungsdatum liegen."
        )

    if not cancellation.items:
        raise InvoiceCancellationStateError(
            "Ein Storno ohne Positionen kann "
            "nicht finalisiert werden."
        )

    charging_sessions = []
    monthly_base_fee_charges = []

    for cancellation_item in cancellation.items:
        original_item = (
            cancellation_item.reversed_invoice_item
        )

        if original_item is None:
            raise InvoiceCancellationStateError(
                "Eine Stornoposition besitzt keine "
                "zugehörige Originalposition."
            )

        if (
            original_item.invoice_id
            != original_invoice.id
        ):
            raise InvoiceCancellationStateError(
                "Eine Stornoposition verweist nicht "
                "auf die Originalrechnung."
            )

        if (
            cancellation_item.item_type
            != original_item.item_type
        ):
            raise InvoiceCancellationStateError(
                "Der Typ der Stornoposition stimmt "
                "nicht mit der Originalposition "
                "überein."
            )

        if original_item.item_type == "charging_session":
            charging_session = (
                original_item.charging_session
            )

            if charging_session is None:
                raise InvoiceCancellationStateError(
                    "Der Originalposition ist kein "
                    "Ladevorgang zugeordnet."
                )

            if (
                not charging_session.invoiced
                or charging_session.invoice_id
                != original_invoice.id
            ):
                raise InvoiceCancellationStateError(
                    "Der Ladevorgang ist nicht mehr "
                    "der Originalrechnung zugeordnet."
                )

            charging_sessions.append(
                charging_session
            )
            continue

        if original_item.item_type == "monthly_base_fee":
            base_fee_charge = (
                original_item.monthly_base_fee_charge
            )

            if base_fee_charge is None:
                raise InvoiceCancellationStateError(
                    "Der Originalposition ist keine "
                    "Grundgebühr zugeordnet."
                )

            if (
                cancellation_item
                .monthly_base_fee_charge_id
                != base_fee_charge.id
            ):
                raise InvoiceCancellationStateError(
                    "Die Stornoposition verweist nicht "
                    "auf die Grundgebühr der "
                    "Originalposition."
                )

            if (
                not base_fee_charge.invoiced
                or base_fee_charge.invoice_id
                != original_invoice.id
            ):
                raise InvoiceCancellationStateError(
                    "Die Grundgebühr ist nicht mehr "
                    "der Originalrechnung zugeordnet."
                )

            monthly_base_fee_charges.append(
                base_fee_charge
            )
            continue

        if original_item.item_type == "postal_delivery":
            continue

        raise InvoiceCancellationStateError(
            "Die Originalposition "
            f"{original_item.id} besitzt den "
            f"unbekannten Typ "
            f"{original_item.item_type!r}."
        )

    timestamp = utc_now()

    cancellation.invoice_number = (
        create_cancellation_number(
            db,
            issue_date=issue_date,
        )
    )
    cancellation.status = "finalized"
    cancellation.issue_date = issue_date
    cancellation.due_date = None
    cancellation.finalized_at = timestamp
    cancellation.cancelled_at = timestamp

    for charging_session in charging_sessions:
        charging_session.invoiced = False
        charging_session.invoice_id = None

    for base_fee_charge in (
        monthly_base_fee_charges
    ):
        base_fee_charge.invoiced = False
        base_fee_charge.invoice_id = None

    try:
        db.commit()

        finalized_cancellation = db.scalar(
            select(Invoice)
            .options(
                selectinload(Invoice.items),
                selectinload(
                    Invoice.original_invoice
                ),
            )
            .where(
                Invoice.id == cancellation.id
            )
        )

        if finalized_cancellation is None:
            raise InvoiceCancellationError(
                "Das finalisierte Storno konnte "
                "nicht geladen werden."
            )

        return finalized_cancellation

    except Exception:
        db.rollback()
        raise
