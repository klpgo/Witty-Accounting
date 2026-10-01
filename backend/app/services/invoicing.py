from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.i18n import normalize_language, translate
from app.utils import locale_format
from app.services.wallboxes import refresh_station_names
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
from app.services.pricing import price_charging_session

from app.utils.utc import utc_now

from app.config import settings


FOUR_DECIMALS = Decimal("0.0001")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")


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
    billed_days: Decimal
    days_in_month: int
    charge: MonthlyBaseFeeCharge | None
    rebill_source_item_id: int | None
    net_amount: Decimal
    vat_rate: Decimal


@dataclass(frozen=True)
class MonthlyBaseFeeAssignmentPeriod:
    assignment: RFIDCardAssignment
    fee_month: date
    billed_days: Decimal
    days_in_month: int


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


def chronological_positions(
    fee_candidates: list[MonthlyBaseFeeCandidate],
    charging_sessions: list,
) -> tuple[list[int], list[int]]:
    """
    Positionsnummern in chronologischer Reihenfolge, Monat für Monat:
    zuerst die Monatsgebühr(en) des Monats, danach dessen Ladevorgänge
    nach Beginn. Rückgabe: (Positionen der Gebühren, Positionen der
    Ladevorgänge) in der Reihenfolge der übergebenen Listen.
    """
    entries = []

    for index, candidate in enumerate(fee_candidates):
        month = (candidate.fee_month.year, candidate.fee_month.month)
        entries.append((month, 0, datetime.min, index, "fee", index))

    for index, (charging_session, _rebill) in enumerate(charging_sessions):
        start = charging_session.start_time
        entries.append(((start.year, start.month), 1, start, index, "session", index))

    entries.sort(key=lambda entry: entry[:4])

    fee_positions = [0] * len(fee_candidates)
    session_positions = [0] * len(charging_sessions)

    for position, entry in enumerate(entries, start=1):
        if entry[4] == "fee":
            fee_positions[entry[5]] = position
        else:
            session_positions[entry[5]] = position

    return fee_positions, session_positions


def format_billed_days(
    value: Decimal,
    locale: str | None = None,
) -> str:
    normalized = value.quantize(
        FOUR_DECIMALS,
        rounding=ROUND_HALF_UP,
    ).normalize()

    return format(normalized, "f").replace(
        ".",
        locale_format.locale_format(locale).decimal_separator,
    )


def _effective_assignment_start_date(
    valid_from: datetime,
    *,
    handover: bool,
) -> date:
    # Beginnt eine Zuordnung mitten am Tag und übernimmt sie die Karte von
    # einer anderen Zuordnung, die an diesem Tag endet, zählt der Tag voll
    # für die ALTE Zuordnung – erst der Folgetag gehört der neuen. Ohne
    # Übergabe (z. B. erste Zuordnung einer Karte) zählt der Tag voll für
    # die neue Zuordnung, egal zu welcher Uhrzeit sie beginnt.
    if valid_from.time() == time.min or not handover:
        return valid_from.date()

    return valid_from.date() + timedelta(days=1)


def _is_mid_day_handover(
    db: Session,
    assignment: RFIDCardAssignment,
) -> bool:
    """
    True, wenn die Karte am ersten Tag der Zuordnung von einer anderen
    Zuordnung übergeben wird, die an diesem Tag nach 00:00 Uhr endet und
    den Tag deshalb voll erhält.
    """
    valid_from = assignment.valid_from

    if valid_from.time() == time.min:
        return False

    day_start = datetime.combine(valid_from.date(), time.min)
    next_day_start = day_start + timedelta(days=1)

    return bool(
        db.scalar(
            select(func.count(RFIDCardAssignment.id)).where(
                RFIDCardAssignment.rfid_card_id == assignment.rfid_card_id,
                RFIDCardAssignment.id != assignment.id,
                RFIDCardAssignment.valid_to > day_start,
                RFIDCardAssignment.valid_to < next_day_start,
            )
        )
    )


def _effective_assignment_end_date_exclusive(
    valid_to: datetime | None,
) -> date | None:
    # Symmetrisch zum Start: endet eine Zuordnung mitten am
    # Tag, gehört dieser Tag noch vollständig der ALTEN
    # (endenden) Zuordnung - die Grenze liegt also erst am
    # Folgetag. Endet sie exakt um Mitternacht, ist dieser
    # Tag schon nicht mehr Teil der Zuordnung.
    if valid_to is None:
        return None

    if valid_to.time() == time.min:
        return valid_to.date()

    return valid_to.date() + timedelta(days=1)


def find_monthly_base_fee_assignments(
    db: Session,
    *,
    user_id: int,
    service_period_start: datetime,
    service_period_end: datetime,
) -> list[MonthlyBaseFeeAssignmentPeriod]:
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

    result: list[MonthlyBaseFeeAssignmentPeriod] = []

    while month_start < service_period_end:
        next_month_start = _next_month_start(
            month_start
        )

        assignments = list(
            db.scalars(
                select(RFIDCardAssignment)
                .where(
                    RFIDCardAssignment.user_id
                    == user_id,
                    RFIDCardAssignment.valid_from
                    < next_month_start,
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

        month_start_date = month_start.date()
        next_month_start_date = (
            next_month_start.date()
        )

        for assignment in assignments:
            effective_start = max(
                month_start_date,
                _effective_assignment_start_date(
                    assignment.valid_from,
                    handover=_is_mid_day_handover(db, assignment),
                ),
            )

            effective_end_exclusive = (
                _effective_assignment_end_date_exclusive(
                    assignment.valid_to
                )
            )
            effective_end_exclusive = min(
                next_month_start_date,
                effective_end_exclusive
                if effective_end_exclusive
                is not None
                else next_month_start_date,
            )

            if (
                effective_start
                >= effective_end_exclusive
            ):
                continue

            billed_days = Decimal(
                (
                    effective_end_exclusive
                    - effective_start
                ).days
            )

            result.append(
                MonthlyBaseFeeAssignmentPeriod(
                    assignment=assignment,
                    fee_month=month_start.date(),
                    billed_days=billed_days,
                    days_in_month=monthrange(
                        month_start.year,
                        month_start.month,
                    )[1],
                )
            )

        month_start = next_month_start

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

    for assignment_period in (
        find_monthly_base_fee_assignments(
            db,
            user_id=user_id,
            service_period_start=service_period_start,
            service_period_end=service_period_end,
        )
    ):
        assignment = assignment_period.assignment
        fee_month = assignment_period.fee_month
        charge = db.scalar(
            select(MonthlyBaseFeeCharge)
            .where(
                MonthlyBaseFeeCharge.rfid_assignment_id
                == assignment.id,
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

            prorated_net_amount = (
                configured_net_amount
                * assignment_period.billed_days
                / Decimal(
                    assignment_period.days_in_month
                )
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )

            if prorated_net_amount <= 0:
                continue

            candidates.append(
                MonthlyBaseFeeCandidate(
                    assignment=assignment,
                    fee_month=fee_month,
                    billed_days=(
                        assignment_period.billed_days
                    ),
                    days_in_month=(
                        assignment_period.days_in_month
                    ),
                    charge=None,
                    rebill_source_item_id=None,
                    net_amount=prorated_net_amount,
                    vat_rate=configured_vat_rate,
                )
            )
            continue

        if charge.user_id != user_id:
            raise InvoiceDraftError(
                f"The stored base fee for RFID card {assignment.rfid_card_id} "
                f"and month {fee_month:%m.%Y} is assigned to another user."
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

        # Noch nicht abgerechneter Eintrag (z. B. aus einem gelöschten Entwurf
        # oder nach einem Storno): Betrag neu aus Grundgebühr und aktuellen
        # Tagen berechnen – die Tage können sich durch eine geänderte
        # Zuordnung verschoben haben. Ohne eingestellte Grundgebühr bleibt
        # der gespeicherte Betrag.
        if (
            configured_net_amount is not None
            and configured_vat_rate is not None
            and configured_net_amount > 0
        ):
            net_amount = (
                configured_net_amount
                * assignment_period.billed_days
                / Decimal(assignment_period.days_in_month)
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )
            vat_rate = configured_vat_rate
        else:
            net_amount = to_decimal(
                charge.net_amount
            ).quantize(
                FOUR_DECIMALS,
                rounding=ROUND_HALF_UP,
            )
            vat_rate = to_decimal(charge.vat_rate)

        if net_amount <= 0:
            continue

        candidates.append(
            MonthlyBaseFeeCandidate(
                assignment=assignment,
                fee_month=fee_month,
                billed_days=(
                    assignment_period.billed_days
                ),
                days_in_month=(
                    assignment_period.days_in_month
                ),
                charge=charge,
                rebill_source_item_id=(
                    rebill_source_item_id
                ),
                net_amount=net_amount,
                vat_rate=vat_rate.quantize(
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
            "The end of the service period must be after its start."
        )

    user = db.get(User, user_id)

    if user is None:
        raise InvoiceUserNotFoundError(
            f"User {user_id} was not found."
        )

    global_settings = db.get(
        GlobalSettings,
        1,
    )

    effective_service_period_start = (
        service_period_start
    )

    if (
        global_settings is not None
        and global_settings.billing_start_date
        is not None
    ):
        billing_start = datetime.combine(
            global_settings.billing_start_date,
            time.min,
        )

        if service_period_end <= billing_start:
            raise NoBillableSessionsError(
                "The selected service period lies entirely before the "
                f"billing start date {global_settings.billing_start_date:%d.%m.%Y}"
                ". Charging sessions and base fees before this date are not "
                "billed."
            )

        effective_service_period_start = max(
            service_period_start,
            billing_start,
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
                >= effective_service_period_start,
                ChargingSession.end_time
                <= service_period_end,
                ChargingSession.invoiced.is_(False),
                ChargingSession.discarded_at.is_(None),
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
            if (
                charging_session.cost_grid_net
                is None
                or charging_session.cost_pv_net
                is None
                or charging_session.vat_rate is None
            ):
                pricing_status = price_charging_session(
                    db,
                    charging_session,
                )

                if pricing_status == "missing_price":
                    raise MissingEnergyPriceError(
                        f"No valid tariff for charging session {charging_session.id} "
                        f"on {charging_session.start_time:%d.%m.%Y}."
                    )

                if pricing_status == "invalid_energy":
                    raise InvalidChargingSessionError(
                        f"Invalid energy values for charging session {charging_session.id}"
                        "."
                    )

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
            service_period_start=(
                effective_service_period_start
            ),
            service_period_end=service_period_end,
        )
    )

    if (
        not charging_sessions
        and not monthly_base_fee_candidates
    ):
        raise NoBillableSessionsError(
            "No billable charging sessions or base fees were found for "
            "this user and period."
        )

    recipient_name = " ".join(
        part
        for part in (
            user.first_name,
            user.last_name,
        )
        if part
    )

    if not user.address:
        raise InvoiceDraftError(
            "No address is stored for the invoice recipient."
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
                global_settings.invoice_issuer_phone,
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
        issuer_phone = normalize_optional_text(
            global_settings.invoice_issuer_phone
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
        issuer_phone = None

    if issuer_name is None:
        raise InvoiceDraftError(
            "No name is configured for the invoice issuer."
        )

    if issuer_address is None:
        raise InvoiceDraftError(
            "No address is configured for the invoice issuer."
        )

    if not issuer_tax_number and not issuer_vat_id:
        raise InvoiceDraftError(
            "A tax number or VAT ID must be configured for the invoice "
            "issuer."
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
        issuer_phone=issuer_phone,
        recipient_name=recipient_name,
        recipient_address=user.address,
        status="draft",
        issue_date=None,
        due_date=None,
        service_period_start=service_period_start,
        service_period_end=service_period_end,
        # Währung und Gebietsschema der Abrechnung festhalten
        currency=(
            getattr(global_settings, "currency", None) or "EUR"
        ),
        locale=(
            getattr(global_settings, "locale", None) or "de-DE"
        ),
        # Sprache des Empfängers, ersatzweise Standardsprache des Mandanten
        language=normalize_language(
            user.language
            or getattr(global_settings, "default_language", None)
        ),
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

        # Stationsnamen aus der Tabelle der Wallboxen (eigener Name, Name aus
        # der Hager Cloud oder Kurzform der ID)
        refresh_station_names(
            db,
            [charging_session for charging_session, _rebill in charging_sessions],
        )

        fee_positions, session_positions = chronological_positions(
            monthly_base_fee_candidates,
            charging_sessions,
        )

        for (
            charging_session,
            rebill_source_item_id,
        ), position_number in zip(
            charging_sessions,
            session_positions,
        ):
            energy_price = find_energy_price(
                db,
                charging_session.start_time,
            )

            if energy_price is None:
                raise MissingEnergyPriceError(
                    f"No valid tariff for charging session {charging_session.id}."
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
                    f"Invalid energy values for charging session {charging_session.id}"
                    "."
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
                description=translate(
                    invoice.language,
                    "item.chargingSession",
                    start=(
                        locale_format.format_date(
                            charging_session.start_time.date(),
                            invoice.locale,
                        )
                        + f" {charging_session.start_time:%H:%M}"
                    ),
                    station=charging_session.station_id,
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
        for candidate, position_number in zip(
            monthly_base_fee_candidates,
            fee_positions,
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
                # noch nicht abgerechnet: Betrag neu übernehmen (z. B. nach
                # geändertem Beginn der Zuordnung oder neuer Grundgebühr)
                charge.net_amount = candidate.net_amount
                charge.vat_rate = candidate.vat_rate
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
            month_name = translate(
                invoice.language,
                f"month.{candidate.fee_month.month}",
            )
            proration_suffix = ""

            if candidate.billed_days != Decimal(
                candidate.days_in_month
            ):
                proration_suffix = translate(
                    invoice.language,
                    "item.proration",
                    days=format_billed_days(
                        candidate.billed_days,
                        invoice.locale,
                    ),
                    total=candidate.days_in_month,
                )

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
                    description=translate(
                        invoice.language,
                        "item.monthlyFee",
                        card=card_label,
                        month=month_name,
                        year=candidate.fee_month.year,
                        proration=proration_suffix,
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
                    description=translate(
                        invoice.language,
                        "item.postage",
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
            f"Invoice {invoice_id} was not found."
        )

    if invoice.status != "draft":
        raise InvoiceAlreadyFinalizedError(
            f"Invoice {invoice_id} is already finalized."
        )

    if not invoice.items:
        raise EmptyInvoiceError(
            "An invoice without line items cannot be finalized."
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
            "The configured payment term must not be negative."
        )

    final_due_date = (
        due_date
        if due_date is not None
        else final_issue_date
        + timedelta(days=payment_term_days)
    )

    if final_due_date < final_issue_date:
        raise InvalidDueDateError(
            "The payment due date must not be before the invoice date."
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
                        f"No charging session is assigned to charging line item {item.id}"
                        "."
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
                            f"Charging session {charging_session.id} has already been "
                            "invoiced."
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
                        f"No base fee is assigned to base fee line item {item.id}."
                    )

                if (
                    base_fee_charge.invoiced
                    or base_fee_charge.invoice_id
                    != invoice.id
                ):
                    raise InvoiceItemStateError(
                        f"Base fee {base_fee_charge.id} is no longer assigned to this "
                        "invoice draft."
                    )

                base_fee_charge.invoiced = True
                base_fee_charge.invoice_id = (
                    invoice.id
                )
                continue

            if item.item_type == "postal_delivery":
                continue

            raise InvoiceItemStateError(
                f"Invoice line item {item.id} has the unknown type {item.item_type!r}"
                "."
            )

        db.commit()
        db.refresh(invoice)

        return invoice

    except Exception:
        db.rollback()
        raise
