from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.invoice import Invoice, InvoiceItem
from app.models.rfid_card import RFIDCard
from app.models.user import User

from app.utils.utc import utc_now

from app.config import settings


FOUR_DECIMALS = Decimal("0.0001")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class InvoiceDraftError(Exception):
    """Base exception for invoice draft creation."""


class InvalidServicePeriodError(InvoiceDraftError):
    """Raised when the service period is invalid."""


class InvoiceUserNotFoundError(InvoiceDraftError):
    """Raised when the requested user does not exist."""


class NoBillableSessionsError(InvoiceDraftError):
    """Raised when no billable sessions were found."""


class MissingEnergyPriceError(InvoiceDraftError):
    """Raised when no applicable tariff exists."""


class InvalidChargingSessionError(InvoiceDraftError):
    """Raised when a charging session contains invalid values."""


class InvoiceNotFoundError(InvoiceDraftError):
    """Raised when an invoice does not exist."""


class InvoiceAlreadyFinalizedError(
    InvoiceDraftError
):
    """Raised when an invoice is already finalized."""


class EmptyInvoiceError(InvoiceDraftError):
    """Raised when an invoice has no items."""


class InvoiceSessionAlreadyInvoicedError(
    InvoiceDraftError
):
    """Raised when an invoice item is already billed."""


class InvalidDueDateError(InvoiceDraftError):
    """Raised when the due date precedes the issue date."""


def to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def find_energy_price(
    db: Session,
    start_time: datetime,
) -> EnergyPrice | None:
    return db.scalar(
        select(EnergyPrice)
        .where(
            EnergyPrice.valid_from <= start_time
        )
        .order_by(
            EnergyPrice.valid_from.desc()
        )
        .limit(1)
    )

    recipient_name = " ".join(
        part
        for part in (
            user.salutation,
            user.first_name,
            user.last_name,
        )
        if part
    )

    if not user.address:
        raise InvoiceDraftError(
            "Für den Rechnungsempfänger ist "
            "keine Anschrift hinterlegt."
        )

    issuer_tax_number = (
        settings.invoice_tax_number
    )
    issuer_vat_id = settings.invoice_vat_id

    if not issuer_tax_number and not issuer_vat_id:
        raise InvoiceDraftError(
            "Für den Rechnungsaussteller muss "
            "eine Steuernummer oder USt-IdNr. "
            "konfiguriert sein."
        )


def get_rebill_source_item_id(
    db: Session,
    *,
    charging_session_id: int,
) -> tuple[bool, int | None]:
    billing_rows = list(
        db.execute(
            select(
                InvoiceItem,
                Invoice.status,
            )
            .join(
                Invoice,
                InvoiceItem.invoice_id == Invoice.id,
            )
            .where(
                InvoiceItem.charging_session_id
                == charging_session_id,
                Invoice.document_type == "invoice",
            )
            .order_by(
                InvoiceItem.id.desc()
            )
        ).all()
    )

    # Noch nie abgerechnet.
    if not billing_rows:
        return True, None

    # Eine Sitzung darf nicht gleichzeitig in mehreren
    # Rechnungsentwürfen enthalten sein.
    if any(
        invoice_status == "draft"
        for _, invoice_status in billing_rows
    ):
        return False, None

    for billing_item, invoice_status in billing_rows:
        if invoice_status != "finalized":
            continue

        rebilled_item_id = db.scalar(
            select(InvoiceItem.id)
            .where(
                InvoiceItem.rebills_invoice_item_id
                == billing_item.id
            )
        )

        if rebilled_item_id is not None:
            continue

        finalized_cancellation_item_id = db.scalar(
            select(InvoiceItem.id)
            .join(
                Invoice,
                InvoiceItem.invoice_id == Invoice.id,
            )
            .where(
                InvoiceItem.reversed_invoice_item_id
                == billing_item.id,
                Invoice.document_type
                == "cancellation",
                Invoice.status == "finalized",
            )
        )

        if finalized_cancellation_item_id is not None:
            return True, billing_item.id

    return False, None


def create_invoice_draft(
    db: Session,
    *,
    user_id: int,
    service_period_start: datetime,
    service_period_end: datetime,
) -> Invoice:
    if service_period_start >= service_period_end:
        raise InvalidServicePeriodError(
            "Das Ende des Leistungszeitraums "
            "muss nach dem Beginn liegen."
        )

    user = db.get(User, user_id)

    if user is None:
        raise InvoiceUserNotFoundError(
            f"Benutzer {user_id} wurde nicht gefunden."
        )

    candidate_sessions = list(
        db.scalars(
            select(ChargingSession)
            .join(
                RFIDCard,
                ChargingSession.rfid_card_id
                == RFIDCard.id,
            )
            .where(
                RFIDCard.user_id == user_id,
                ChargingSession.start_time
                >= service_period_start,
                ChargingSession.end_time
                <= service_period_end,
                ChargingSession.invoiced.is_(False),
                ChargingSession.cost_grid_net.is_not(
                    None
                ),
                ChargingSession.cost_pv_net.is_not(
                    None
                ),
                ChargingSession.vat_rate.is_not(
                    None
                ),
            )
            .order_by(
                ChargingSession.start_time,
                ChargingSession.id,
            )
            .with_for_update()
        ).all()
    )

    charging_sessions: list[
        tuple[ChargingSession, int | None]
    ] = []

    for charging_session in candidate_sessions:
        is_billable, rebill_source_item_id = (
            get_rebill_source_item_id(
                db,
                charging_session_id=(
                    charging_session.id
                ),
            )
        )

        if is_billable:
            charging_sessions.append(
                (
                    charging_session,
                    rebill_source_item_id,
                )
            )

    if not charging_sessions:
        raise NoBillableSessionsError(
            "Für diesen Benutzer und Zeitraum "
            "wurden keine abrechenbaren "
            "Ladevorgänge gefunden."
        )

    recipient_name = " ".join(
        part
        for part in (
            user.salutation,
            user.first_name,
            user.last_name,
        )
        if part
    )

    if not user.address:
        raise InvoiceDraftError(
            "Für den Rechnungsempfänger ist "
            "keine Anschrift hinterlegt."
        )

    issuer_tax_number = settings.invoice_tax_number
    issuer_vat_id = settings.invoice_vat_id

    if not issuer_tax_number and not issuer_vat_id:
        raise InvoiceDraftError(
            "Für den Rechnungsaussteller muss "
            "eine Steuernummer oder USt-IdNr. "
            "konfiguriert sein."
        )

    invoice = Invoice(
        invoice_number=None,
        document_type="invoice",
        original_invoice_id=None,
        cancellation_reason=None,
        cancelled_at=None,
        user_id=user_id,
        issuer_name=settings.invoice_issuer_name,
        issuer_address=settings.invoice_issuer_address,
        issuer_tax_number=issuer_tax_number,
        issuer_vat_id=issuer_vat_id,
        recipient_name=recipient_name,
        recipient_address=user.address,
        status="draft",
        issue_date=None,
        due_date=None,
        service_period_start=service_period_start,
        service_period_end=service_period_end,
        currency="EUR",
        total_net=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total_gross=Decimal("0.00"),
        finalized_at=None,
        pdf_storage_path=None,
        pdf_sha256=None,
        pdf_size_bytes=None,
        pdf_created_at=None,
    )

    total_net = Decimal("0.00")
    total_vat = Decimal("0.00")
    total_gross = Decimal("0.00")

    try:
        db.add(invoice)
        db.flush()

        for position_number, (
            charging_session,
            rebill_source_item_id,
        ) in enumerate(
            charging_sessions,
            start=1,
        ):
            energy_price = find_energy_price(
                db,
                charging_session.start_time,
            )

            if energy_price is None:
                raise MissingEnergyPriceError(
                    "Kein gültiger Tarif für "
                    f"Ladevorgang {charging_session.id}."
                )

            energy_total = to_decimal(
                charging_session.energy_total_kwh
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            energy_pv = to_decimal(
                charging_session.energy_pv_kwh
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            energy_grid = (
                energy_total - energy_pv
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            if (
                energy_total < 0
                or energy_pv < 0
                or energy_grid < 0
            ):
                raise InvalidChargingSessionError(
                    "Ungültige Energiemengen bei "
                    f"Ladevorgang {charging_session.id}."
                )

            cost_grid = to_decimal(
                charging_session.cost_grid_net
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            cost_pv = to_decimal(
                charging_session.cost_pv_net
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            net_amount = (
                cost_grid + cost_pv
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            vat_rate = to_decimal(
                charging_session.vat_rate
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )

            net_amount_cents = net_amount.quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )

            vat_amount = (
                net_amount
                * vat_rate
                / HUNDRED
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )

            gross_amount = (
                net_amount_cents + vat_amount
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )

            item = InvoiceItem(
                invoice_id=invoice.id,
                charging_session_id=(
                    charging_session.id
                ),
                reversed_invoice_item_id=None,
                rebills_invoice_item_id=rebill_source_item_id,
                position_number=position_number,
                description=(
                    "Ladevorgang "
                    f"{charging_session.start_time:%d.%m.%Y %H:%M} "
                    f"an {charging_session.station_id}"
                ),
                session_start=(
                    charging_session.start_time
                ),
                session_end=(
                    charging_session.end_time
                ),
                station_id=charging_session.station_id,
                energy_total_kwh=energy_total,
                energy_grid_kwh=energy_grid,
                energy_pv_kwh=energy_pv,
                grid_price_net=to_decimal(
                    energy_price.grid_price_net
                ).quantize(
                    FOUR_DECIMALS,
                    rounding=ROUND_HALF_UP,
                ),
                pv_price_net=to_decimal(
                    energy_price.pv_price_net
                ).quantize(
                    FOUR_DECIMALS,
                    rounding=ROUND_HALF_UP,
                ),
                cost_grid_net=cost_grid,
                cost_pv_net=cost_pv,
                net_amount=net_amount,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                gross_amount=gross_amount,
            )

            db.add(item)

            total_net += net_amount_cents
            total_vat += vat_amount
            total_gross += gross_amount

        invoice.total_net = total_net.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )
        invoice.vat_amount = total_vat.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )
        invoice.total_gross = total_gross.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        db.commit()
        db.refresh(invoice)

        return invoice

    except Exception:
        db.rollback()
        raise

def finalize_invoice(
    db: Session,
    *,
    invoice_id: int,
    issue_date: date | None = None,
    due_date: date | None = None,
) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .with_for_update()
    )

    if invoice is None:
        raise InvoiceNotFoundError(
            f"Rechnung {invoice_id} wurde nicht gefunden."
        )

    if invoice.status != "draft":
        raise InvoiceAlreadyFinalizedError(
            f"Rechnung {invoice_id} ist bereits finalisiert."
        )

    if not invoice.items:
        raise EmptyInvoiceError(
            "Eine Rechnung ohne Positionen "
            "kann nicht finalisiert werden."
        )

    final_issue_date = (
        issue_date
        if issue_date is not None
        else utc_now().date()
    )

    payment_term_days = (
        settings.invoice_payment_term_days
    )

    if payment_term_days < 0:
        raise InvalidDueDateError(
            "Die konfigurierte Zahlungsfrist "
            "darf nicht negativ sein."
        )

    final_due_date = (
        due_date
        if due_date is not None
        else final_issue_date
        + timedelta(days=payment_term_days)
    )

    if final_due_date < final_issue_date:
        raise InvalidDueDateError(
            "Das Zahlungsziel darf nicht vor "
            "dem Rechnungsdatum liegen."
        )

    try:
        invoice.invoice_number = (
            f"RE-{final_issue_date.year}-"
            f"{invoice.id:06d}"
        )
        invoice.issue_date = final_issue_date
        invoice.due_date = final_due_date
        invoice.status = "finalized"
        invoice.finalized_at = utc_now()

        for item in invoice.items:
            charging_session = item.charging_session

            if (
                charging_session.invoiced
                or (
                    charging_session.invoice_id
                    is not None
                    and charging_session.invoice_id
                    != invoice.id
                )
            ):
                raise (
                    InvoiceSessionAlreadyInvoicedError(
                        "Ladevorgang "
                        f"{charging_session.id} wurde "
                        "bereits fakturiert."
                    )
                )

            charging_session.invoiced = True
            charging_session.invoice_id = invoice.id

        db.commit()
        db.refresh(invoice)

        return invoice

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

    return (
        f"{prefix}"
        f"{sequence_number:06d}"
    )


def finalize_cancellation(
    db: Session,
    *,
    cancellation_id: int,
    issue_date: date,
) -> Invoice:
    cancellation = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
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

    if (
        cancellation.document_type
        != "cancellation"
    ):
        raise InvoiceCancellationStateError(
            "Nur ein Stornodokument kann über "
            "diese Funktion finalisiert werden."
        )

    if cancellation.status != "draft":
        raise InvoiceCancellationStateError(
            "Nur ein Storno-Entwurf kann "
            "finalisiert werden."
        )

    original_invoice = (
        cancellation.original_invoice
    )

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
        and issue_date
        < original_invoice.issue_date
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
