from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.models.invoice import Invoice, InvoiceItem
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.models.global_settings import GlobalSettings
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)

from app.utils.utc import utc_now

from app.config import settings


FOUR_DECIMALS = Decimal("0.0001")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MONTH_NAMES_DE = (
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


@dataclass(frozen=True)
class MonthlyBaseFeeCandidate:
    assignment: RFIDCardAssignment
    fee_month: date
    charge: MonthlyBaseFeeCharge | None
    rebill_source_item_id: int | None
    net_amount: Decimal
    vat_rate: Decimal


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


class InvoiceItemStateError(InvoiceDraftError):
    """Raised when an invoice item has an invalid state."""

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


def _next_month_start(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(
            year=value.year + 1,
            month=1,
        )

    return value.replace(
        month=value.month + 1,
    )


def find_monthly_base_fee_assignments(
    db: Session,
    *,
    user_id: int,
    service_period_start: datetime,
    service_period_end: datetime,
) -> list[tuple[RFIDCardAssignment, date]]:
    month_start = service_period_start.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    if month_start < service_period_start:
        month_start = _next_month_start(
            month_start
        )

    result: list[
        tuple[RFIDCardAssignment, date]
    ] = []

    while month_start < service_period_end:
        assignments = list(
            db.scalars(
                select(RFIDCardAssignment)
                .where(
                    RFIDCardAssignment.user_id
                    == user_id,
                    RFIDCardAssignment.valid_from
                    <= month_start,
                    or_(
                        RFIDCardAssignment.valid_to
                        .is_(None),
                        RFIDCardAssignment.valid_to
                        > month_start,
                    ),
                )
                .order_by(
                    RFIDCardAssignment.rfid_card_id,
                    RFIDCardAssignment.id,
                )
            ).all()
        )

        result.extend(
            (
                assignment,
                month_start.date(),
            )
            for assignment in assignments
        )

        month_start = _next_month_start(
            month_start
        )

    return result


def get_base_fee_rebill_source_item_id(
    db: Session,
    *,
    monthly_base_fee_charge_id: int,
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
                InvoiceItem.monthly_base_fee_charge_id
                == monthly_base_fee_charge_id,
                InvoiceItem.item_type
                == "monthly_base_fee",
                Invoice.document_type == "invoice",
            )
            .order_by(
                InvoiceItem.id.desc()
            )
        ).all()
    )

    if not billing_rows:
        return True, None

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


def find_billable_monthly_base_fee_candidates(
    db: Session,
    *,
    user_id: int,
    service_period_start: datetime,
    service_period_end: datetime,
) -> list[MonthlyBaseFeeCandidate]:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    configured_net_amount: Decimal | None = None
    configured_vat_rate: Decimal | None = None

    if global_settings is not None:
        configured_net_amount = to_decimal(
            global_settings.monthly_base_fee_net
        ).quantize(
            FOUR_DECIMALS,
            rounding=ROUND_HALF_UP,
        )
        configured_vat_rate = to_decimal(
            global_settings.monthly_base_fee_vat_rate
        ).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

    candidates: list[
        MonthlyBaseFeeCandidate
    ] = []

    for assignment, fee_month in (
        find_monthly_base_fee_assignments(
            db,
            user_id=user_id,
            service_period_start=service_period_start,
            service_period_end=service_period_end,
        )
    ):
        charge = db.scalar(
            select(MonthlyBaseFeeCharge)
            .where(
                MonthlyBaseFeeCharge.rfid_card_id
                == assignment.rfid_card_id,
                MonthlyBaseFeeCharge.fee_month
                == fee_month,
            )
            .with_for_update()
        )

        if charge is None:
            if (
                configured_net_amount is None
                or configured_vat_rate is None
                or configured_net_amount <= 0
            ):
                continue

            candidates.append(
                MonthlyBaseFeeCandidate(
                    assignment=assignment,
                    fee_month=fee_month,
                    charge=None,
                    rebill_source_item_id=None,
                    net_amount=configured_net_amount,
                    vat_rate=configured_vat_rate,
                )
            )
            continue

        if charge.user_id != user_id:
            raise InvoiceDraftError(
                "Die gespeicherte Grundgebühr für "
                f"RFID-Karte {assignment.rfid_card_id} "
                f"und Monat {fee_month:%m.%Y} ist "
                "einem anderen Benutzer zugeordnet."
            )

        if (
            charge.invoiced
            or charge.invoice_id is not None
        ):
            continue

        is_billable, rebill_source_item_id = (
            get_base_fee_rebill_source_item_id(
                db,
                monthly_base_fee_charge_id=charge.id,
            )
        )

        if not is_billable:
            continue

        net_amount = to_decimal(
            charge.net_amount
        ).quantize(
            FOUR_DECIMALS,
            rounding=ROUND_HALF_UP,
        )

        if net_amount <= 0:
            continue

        candidates.append(
            MonthlyBaseFeeCandidate(
                assignment=assignment,
                fee_month=fee_month,
                charge=charge,
                rebill_source_item_id=(
                    rebill_source_item_id
                ),
                net_amount=net_amount,
                vat_rate=to_decimal(
                    charge.vat_rate
                ).quantize(
                    CENT,
                    rounding=ROUND_HALF_UP,
                ),
            )
        )

    return candidates


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
                RFIDCardAssignment,
                ChargingSession.rfid_assignment_id
                == RFIDCardAssignment.id,
            )
            .where(
                RFIDCardAssignment.user_id == user_id,
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

    monthly_base_fee_candidates = (
        find_billable_monthly_base_fee_candidates(
            db,
            user_id=user_id,
            service_period_start=service_period_start,
            service_period_end=service_period_end,
        )
    )

    if (
        not charging_sessions
        and not monthly_base_fee_candidates
    ):
        raise NoBillableSessionsError(
            "Für diesen Benutzer und Zeitraum "
            "wurden keine abrechenbaren "
            "Ladevorgänge oder Grundgebühren "
            "gefunden."
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

    global_settings = db.get(
        GlobalSettings,
        1,
    )

    database_business_settings_configured = (
        global_settings is not None
        and any(
            normalize_optional_text(value)
            is not None
            for value in (
                global_settings.invoice_issuer_name,
                global_settings.invoice_issuer_address,
                global_settings.invoice_tax_number,
                global_settings.invoice_vat_id,
                global_settings.invoice_bank_name,
                global_settings.invoice_iban,
                global_settings.invoice_bic,
            )
        )
    )

    if database_business_settings_configured:
        issuer_name = normalize_optional_text(
            global_settings.invoice_issuer_name
        )
        issuer_address = normalize_optional_text(
            global_settings.invoice_issuer_address
        )
        issuer_tax_number = normalize_optional_text(
            global_settings.invoice_tax_number
        )
        issuer_vat_id = normalize_optional_text(
            global_settings.invoice_vat_id
        )
        issuer_bank_name = normalize_optional_text(
            global_settings.invoice_bank_name
        )
        issuer_iban = normalize_optional_text(
            global_settings.invoice_iban
        )
        issuer_bic = normalize_optional_text(
            global_settings.invoice_bic
        )
    else:
        issuer_name = normalize_optional_text(
            settings.invoice_issuer_name
        )
        issuer_address = normalize_optional_text(
            settings.invoice_issuer_address
        )
        issuer_tax_number = normalize_optional_text(
            settings.invoice_tax_number
        )
        issuer_vat_id = normalize_optional_text(
            settings.invoice_vat_id
        )
        issuer_bank_name = None
        issuer_iban = None
        issuer_bic = None

    if issuer_name is None:
        raise InvoiceDraftError(
            "Für den Rechnungsaussteller ist "
            "kein Name konfiguriert."
        )

    if issuer_address is None:
        raise InvoiceDraftError(
            "Für den Rechnungsaussteller ist "
            "keine Anschrift konfiguriert."
        )

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
        issuer_name=issuer_name,
        issuer_address=issuer_address,
        issuer_tax_number=issuer_tax_number,
        issuer_vat_id=issuer_vat_id,
        issuer_bank_name=issuer_bank_name,
        issuer_iban=issuer_iban,
        issuer_bic=issuer_bic,
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
            start=(
                len(monthly_base_fee_candidates) + 1
            ),
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
                item_type="charging_session",
                monthly_base_fee_charge_id=None,
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
        for position_number, candidate in enumerate(
            monthly_base_fee_candidates,
            start=1,
        ):
            charge = candidate.charge

            if charge is None:
                charge = MonthlyBaseFeeCharge(
                    rfid_card_id=(
                        candidate.assignment.rfid_card_id
                    ),
                    rfid_assignment_id=(
                        candidate.assignment.id
                    ),
                    user_id=user_id,
                    fee_month=candidate.fee_month,
                    net_amount=candidate.net_amount,
                    vat_rate=candidate.vat_rate,
                    invoiced=False,
                    invoice_id=invoice.id,
                )
                db.add(charge)
                db.flush()
            else:
                charge.invoice_id = invoice.id
                charge.invoiced = False

            net_amount = candidate.net_amount
            net_amount_cents = net_amount.quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            vat_amount = (
                net_amount
                * candidate.vat_rate
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

            card = candidate.assignment.rfid_card
            card_label = (
                card.description
                or card.rfid_number
            )
            month_name = MONTH_NAMES_DE[
                candidate.fee_month.month
            ]

            db.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    item_type="monthly_base_fee",
                    monthly_base_fee_charge_id=(
                        charge.id
                    ),
                    charging_session_id=None,
                    reversed_invoice_item_id=None,
                    rebills_invoice_item_id=(
                        candidate.rebill_source_item_id
                    ),
                    position_number=position_number,
                    description=(
                        "Monatsgebühr RFID-Karte "
                        f"{card_label} - "
                        f"{month_name} "
                        f"{candidate.fee_month.year}"
                    ),
                    session_start=None,
                    session_end=None,
                    station_id=None,
                    energy_total_kwh=None,
                    energy_grid_kwh=None,
                    energy_pv_kwh=None,
                    grid_price_net=None,
                    pv_price_net=None,
                    cost_grid_net=None,
                    cost_pv_net=None,
                    net_amount=net_amount,
                    vat_rate=candidate.vat_rate,
                    vat_amount=vat_amount,
                    gross_amount=gross_amount,
                )
            )

            total_net += net_amount_cents
            total_vat += vat_amount
            total_gross += gross_amount

        postal_delivery_fee_net = (
            to_decimal(
                global_settings.postal_delivery_fee_net
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )
            if (
                global_settings is not None
                and user.invoice_delivery_post
                and not user.invoice_delivery_email
            )
            else Decimal("0.0000")
        )

        if postal_delivery_fee_net > 0:
            shared_fee_vat_rate = to_decimal(
                global_settings
                .monthly_base_fee_vat_rate
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            postal_delivery_fee_net_cents = (
                postal_delivery_fee_net.quantize(
                    CENT,
                    rounding=ROUND_HALF_UP,
                )
            )
            postal_delivery_fee_vat = (
                postal_delivery_fee_net
                * shared_fee_vat_rate
                / HUNDRED
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            postal_delivery_fee_gross = (
                postal_delivery_fee_net_cents
                + postal_delivery_fee_vat
            ).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )

            db.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    item_type="postal_delivery",
                    monthly_base_fee_charge_id=None,
                    charging_session_id=None,
                    reversed_invoice_item_id=None,
                    rebills_invoice_item_id=None,
                    position_number=(
                        len(monthly_base_fee_candidates)
                        + len(charging_sessions)
                        + 1
                    ),
                    description="Briefporto",
                    session_start=None,
                    session_end=None,
                    station_id=None,
                    energy_total_kwh=None,
                    energy_grid_kwh=None,
                    energy_pv_kwh=None,
                    grid_price_net=None,
                    pv_price_net=None,
                    cost_grid_net=None,
                    cost_pv_net=None,
                    net_amount=postal_delivery_fee_net,
                    vat_rate=shared_fee_vat_rate,
                    vat_amount=postal_delivery_fee_vat,
                    gross_amount=(
                        postal_delivery_fee_gross
                    ),
                )
            )

            total_net += postal_delivery_fee_net_cents
            total_vat += postal_delivery_fee_vat
            total_gross += postal_delivery_fee_gross

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

    global_settings = db.get(
        GlobalSettings,
        1,
    )

    payment_term_days = (
        global_settings.invoice_payment_term_days
        if global_settings is not None
        else settings.invoice_payment_term_days
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

    invoice_number_prefix = (
        normalize_optional_text(
            global_settings.invoice_number_prefix
        )
        if global_settings is not None
        else None
    ) or "RE"

    try:
        invoice.invoice_number = (
            f"{invoice_number_prefix}-"
            f"{final_issue_date.year}-"
            f"{invoice.id:06d}"
        )
        invoice.issue_date = final_issue_date
        invoice.due_date = final_due_date
        invoice.status = "finalized"
        invoice.finalized_at = utc_now()

        for item in invoice.items:
            if item.item_type == "charging_session":
                charging_session = (
                    item.charging_session
                )

                if charging_session is None:
                    raise InvoiceItemStateError(
                        "Der Ladeposition "
                        f"{item.id} ist kein "
                        "Ladevorgang zugeordnet."
                    )

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
                            f"{charging_session.id} "
                            "wurde bereits fakturiert."
                        )
                    )

                charging_session.invoiced = True
                charging_session.invoice_id = (
                    invoice.id
                )
                continue

            if item.item_type == "monthly_base_fee":
                base_fee_charge = (
                    item.monthly_base_fee_charge
                )

                if base_fee_charge is None:
                    raise InvoiceItemStateError(
                        "Der Grundgebührenposition "
                        f"{item.id} ist keine "
                        "Grundgebühr zugeordnet."
                    )

                if (
                    base_fee_charge.invoiced
                    or base_fee_charge.invoice_id
                    != invoice.id
                ):
                    raise InvoiceItemStateError(
                        "Die Grundgebühr "
                        f"{base_fee_charge.id} ist "
                        "nicht mehr diesem "
                        "Rechnungsentwurf zugeordnet."
                    )

                base_fee_charge.invoiced = True
                base_fee_charge.invoice_id = (
                    invoice.id
                )
                continue

            if item.item_type == "postal_delivery":
                continue

            raise InvoiceItemStateError(
                "Die Rechnungsposition "
                f"{item.id} besitzt den unbekannten "
                f"Typ {item.item_type!r}."
            )

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
