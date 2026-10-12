"""
Rechnungen und Abrechnungsdaten nach Ablauf der Aufbewahrungsfrist löschen.

Die Frist beginnt mit dem Ende des Kalenderjahres, in dem die Rechnung
ausgestellt wurde. Bei 10 Jahren ist eine Rechnung aus 2026 also bis
31.12.2036 aufzubewahren und ab 1.1.2037 löschbar.

Gelöscht wird jahrweise und nur auf Anforderung eines Administrators:

- Rechnungen samt Positionen und archivierten PDFs. Eine Rechnung und ihre
  Stornorechnung bilden eine Gruppe; sie zählt zum späteren der beiden
  Ausstellungsjahre und wird nur gemeinsam gelöscht.
- Ladevorgänge und Grundgebühren, die nur in diesen Rechnungen
  abgerechnet wurden – auch von Kunden, die noch aktiv sind.
- verworfene Ladevorgänge und Merkmale gelöschter Ladevorgänge aus dem
  gelöschten Zeitraum.

Jahre werden in zeitlicher Reihenfolge gelöscht. Danach werden Ladevorgänge
aus gelöschten Jahren nicht mehr importiert. Jeder Löschlauf wird im
Löschprotokoll (retention_purges) festgehalten.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.deleted_charging_session import (
    DeletedChargingSession,
)
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice, InvoiceItem
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.models.retention_purge import RetentionPurge
from app.services.invoice_archive import (
    InvoiceArchiveError,
    get_archive_root,
    resolve_archive_path,
)
from app.utils.local_time import local_now


DEFAULT_RETENTION_YEARS = 10
MIN_RETENTION_YEARS = 6
MAX_RETENTION_YEARS = 30


class InvoiceRetentionError(Exception):
    """Base exception for purging expired invoices."""


class RetentionPurgeBlockedError(InvoiceRetentionError):
    """Raised when a year cannot be purged (yet)."""


@dataclass(frozen=True)
class YearBlocker:
    code: str
    count: int
    message: str


@dataclass
class InvoiceGroup:
    invoice_id: int
    invoice_number: str | None
    member_ids: list[int]
    cancellations: int
    year: int
    pdf_paths: list[str]
    has_draft_cancellation: bool = False


@dataclass
class YearOverview:
    year: int
    invoices: int = 0
    cancellations: int = 0
    pdf_files: int = 0
    first_invoice_number: str | None = None
    last_invoice_number: str | None = None
    blockers: list[YearBlocker] = field(default_factory=list)

    @property
    def purgeable(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "invoices": self.invoices,
            "cancellations": self.cancellations,
            "pdf_files": self.pdf_files,
            "first_invoice_number": self.first_invoice_number,
            "last_invoice_number": self.last_invoice_number,
            "purgeable": self.purgeable,
            "blockers": [
                {
                    "code": blocker.code,
                    "count": blocker.count,
                    "message": blocker.message,
                }
                for blocker in self.blockers
            ],
        }


@dataclass(frozen=True)
class PurgeResult:
    year: int
    invoices: int
    cancellations: int
    pdf_files: int
    charging_sessions: int
    base_fees: int
    pdf_errors: list[str]
    protocol_id: int


def load_settings(db: Session) -> GlobalSettings:
    settings = db.get(GlobalSettings, 1)

    if settings is None:
        settings = GlobalSettings(id=1)
        db.add(settings)
        db.flush()

    return settings


def retention_years_of(settings: GlobalSettings | None) -> int:
    value = (
        settings.invoice_retention_years
        if settings is not None
        else None
    )

    return int(value) if value else DEFAULT_RETENTION_YEARS


def last_purgeable_year(
    retention_years: int,
    today: date,
) -> int:
    """Letztes Ausstellungsjahr, dessen Aufbewahrungsfrist abgelaufen ist."""
    return today.year - retention_years - 1


def year_end(year: int) -> datetime:
    """Beginn des Folgejahres (exklusive Grenze)."""
    return datetime(year + 1, 1, 1)


def load_groups(db: Session) -> list[InvoiceGroup]:
    """Rechnungen mit ihrer Stornorechnung als Gruppen (ohne Entwürfe)."""
    rows = db.execute(
        select(
            Invoice.id,
            Invoice.invoice_number,
            Invoice.document_type,
            Invoice.status,
            Invoice.issue_date,
            Invoice.original_invoice_id,
            Invoice.pdf_storage_path,
        )
    ).all()

    originals = {
        row.id: row
        for row in rows
        if row.document_type != "cancellation"
        and row.status == "finalized"
        and row.issue_date is not None
    }
    cancellations: dict[int, Any] = {
        row.original_invoice_id: row
        for row in rows
        if row.document_type == "cancellation"
        and row.original_invoice_id is not None
    }

    groups: list[InvoiceGroup] = []

    for invoice in originals.values():
        member_ids = [invoice.id]
        pdf_paths = (
            [invoice.pdf_storage_path]
            if invoice.pdf_storage_path
            else []
        )
        year = invoice.issue_date.year
        cancellation_count = 0
        has_draft_cancellation = False

        cancellation = cancellations.get(invoice.id)

        if cancellation is not None:
            member_ids.append(cancellation.id)

            if (
                cancellation.status == "finalized"
                and cancellation.issue_date is not None
            ):
                cancellation_count = 1
                year = max(year, cancellation.issue_date.year)

                if cancellation.pdf_storage_path:
                    pdf_paths.append(cancellation.pdf_storage_path)
            else:
                has_draft_cancellation = True

        groups.append(
            InvoiceGroup(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                member_ids=member_ids,
                cancellations=cancellation_count,
                year=year,
                pdf_paths=pdf_paths,
                has_draft_cancellation=has_draft_cancellation,
            )
        )

    return groups


def _year_blockers(
    db: Session,
    *,
    year: int,
    groups: list[InvoiceGroup],
) -> list[YearBlocker]:
    blockers: list[YearBlocker] = []
    boundary = year_end(year)

    older = {
        group.year
        for group in groups
        if group.year < year
    }

    if older:
        blockers.append(
            YearBlocker(
                code="older_year_pending",
                count=min(older),
                message=(
                    f"The year {min(older)} must be deleted first."
                ),
            )
        )

    draft_cancellations = sum(
        1
        for group in groups
        if group.year == year and group.has_draft_cancellation
    )

    if draft_cancellations:
        blockers.append(
            YearBlocker(
                code="draft_cancellations",
                count=draft_cancellations,
                message=(
                    f"{draft_cancellations} cancellation draft(s) must be "
                    "finalized or deleted first."
                ),
            )
        )

    draft_invoices = int(
        db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.status == "draft",
                Invoice.document_type != "cancellation",
                Invoice.service_period_start < boundary,
            )
        )
        or 0
    )

    if draft_invoices:
        blockers.append(
            YearBlocker(
                code="draft_invoices",
                count=draft_invoices,
                message=(
                    f"{draft_invoices} draft invoice(s) for {year} or "
                    "earlier must be finalized or deleted first."
                ),
            )
        )

    unbilled_sessions = int(
        db.scalar(
            select(func.count(ChargingSession.id)).where(
                ChargingSession.start_time < boundary,
                ChargingSession.invoiced.is_not(True),
                ChargingSession.discarded_at.is_(None),
            )
        )
        or 0
    )

    if unbilled_sessions:
        blockers.append(
            YearBlocker(
                code="unbilled_charging_sessions",
                count=unbilled_sessions,
                message=(
                    f"{unbilled_sessions} charging session(s) from {year} "
                    "or earlier have not been billed or discarded."
                ),
            )
        )

    unbilled_fees = int(
        db.scalar(
            select(func.count(MonthlyBaseFeeCharge.id)).where(
                MonthlyBaseFeeCharge.fee_month < boundary.date(),
                MonthlyBaseFeeCharge.invoiced.is_(False),
            )
        )
        or 0
    )

    if unbilled_fees:
        blockers.append(
            YearBlocker(
                code="unbilled_base_fees",
                count=unbilled_fees,
                message=(
                    f"{unbilled_fees} base fee(s) from {year} or earlier "
                    "have not been billed."
                ),
            )
        )

    return blockers


def build_overview(
    db: Session,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    settings = db.get(GlobalSettings, 1)
    retention_years = retention_years_of(settings)
    current_day = today or local_now().date()
    cutoff = last_purgeable_year(retention_years, current_day)
    groups = load_groups(db)

    years: dict[int, YearOverview] = {}

    for group in groups:
        if group.year > cutoff:
            continue

        overview = years.setdefault(
            group.year,
            YearOverview(year=group.year),
        )
        overview.invoices += 1
        overview.cancellations += group.cancellations
        overview.pdf_files += len(group.pdf_paths)

    for overview in years.values():
        numbers = sorted(
            group.invoice_number
            for group in groups
            if group.year == overview.year and group.invoice_number
        )

        if numbers:
            overview.first_invoice_number = numbers[0]
            overview.last_invoice_number = numbers[-1]

        overview.blockers = _year_blockers(
            db,
            year=overview.year,
            groups=groups,
        )

    protocol = db.scalars(
        select(RetentionPurge).order_by(
            RetentionPurge.purged_at.desc(),
            RetentionPurge.id.desc(),
        )
    ).all()

    return {
        "retention_years": retention_years,
        "min_retention_years": MIN_RETENTION_YEARS,
        "max_retention_years": MAX_RETENTION_YEARS,
        "last_purgeable_year": cutoff,
        "purged_through_year": (
            settings.retention_purged_through_year
            if settings is not None
            else None
        ),
        "years": [
            years[year].as_dict()
            for year in sorted(years)
        ],
        "protocol": [
            {
                "id": entry.id,
                "year": entry.year,
                "retention_years": entry.retention_years,
                "invoices": entry.invoices,
                "cancellations": entry.cancellations,
                "first_invoice_number": entry.first_invoice_number,
                "last_invoice_number": entry.last_invoice_number,
                "pdf_files": entry.pdf_files,
                "charging_sessions": entry.charging_sessions,
                "base_fees": entry.base_fees,
                "pdf_errors": (
                    entry.pdf_errors.splitlines()
                    if entry.pdf_errors
                    else []
                ),
                "purged_by": entry.purged_by,
                "purged_at": entry.purged_at,
            }
            for entry in protocol
        ],
    }


def oldest_purgeable_year(
    db: Session,
    *,
    today: date | None = None,
) -> int | None:
    """Ältestes Jahr, dessen Frist abgelaufen ist (für den Hinweis auf dem
    Dashboard) – unabhängig davon, ob noch etwas die Löschung sperrt."""
    settings = db.get(GlobalSettings, 1)
    cutoff = last_purgeable_year(
        retention_years_of(settings),
        today or local_now().date(),
    )
    years = [
        group.year
        for group in load_groups(db)
        if group.year <= cutoff
    ]

    return min(years) if years else None


def set_retention_years(db: Session, years: int) -> int:
    if not MIN_RETENTION_YEARS <= years <= MAX_RETENTION_YEARS:
        raise InvoiceRetentionError(
            f"The retention period must be between {MIN_RETENTION_YEARS} "
            f"and {MAX_RETENTION_YEARS} years."
        )

    settings = load_settings(db)
    settings.invoice_retention_years = years
    db.commit()

    return years


def _remove_pdf_files(
    db: Session,
    paths: list[str],
    archive_root: Path | None,
) -> tuple[int, list[str]]:
    try:
        root = get_archive_root(archive_root, db=db)
    except InvoiceArchiveError:
        return 0, list(paths)

    removed = 0
    errors: list[str] = []
    directories: set[Path] = set()

    for relative_path in paths:
        try:
            absolute_path = resolve_archive_path(root, relative_path)
            absolute_path.unlink(missing_ok=True)
            removed += 1
            directories.add(absolute_path.parent)
        except (InvoiceArchiveError, OSError):
            errors.append(relative_path)

    # leere Jahresordner entfernen
    for directory in directories:
        try:
            if directory != root and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            pass

    return removed, errors


def purge_year(
    db: Session,
    *,
    year: int,
    confirm_year: int,
    purged_by: str | None = None,
    today: date | None = None,
    archive_root: Path | None = None,
) -> PurgeResult:
    if confirm_year != year:
        raise InvoiceRetentionError(
            "The confirmation does not match the year to be deleted."
        )

    settings = load_settings(db)
    retention_years = retention_years_of(settings)
    cutoff = last_purgeable_year(
        retention_years,
        today or local_now().date(),
    )

    if year > cutoff:
        raise RetentionPurgeBlockedError(
            f"The retention period for {year} has not expired yet "
            f"(latest year that can be deleted: {cutoff})."
        )

    groups = load_groups(db)
    year_groups = [group for group in groups if group.year == year]

    if not year_groups:
        raise RetentionPurgeBlockedError(
            f"There are no invoices from {year} to delete."
        )

    blockers = _year_blockers(db, year=year, groups=groups)

    if blockers:
        raise RetentionPurgeBlockedError(
            "The year cannot be deleted yet: "
            + "; ".join(blocker.message for blocker in blockers)
        )

    invoice_ids = [
        member_id
        for group in year_groups
        for member_id in group.member_ids
    ]
    pdf_paths = [
        path
        for group in year_groups
        for path in group.pdf_paths
    ]
    numbers = sorted(
        group.invoice_number
        for group in year_groups
        if group.invoice_number
    )
    boundary = year_end(year)

    item_rows = db.execute(
        select(
            InvoiceItem.id,
            InvoiceItem.charging_session_id,
            InvoiceItem.monthly_base_fee_charge_id,
        ).where(InvoiceItem.invoice_id.in_(invoice_ids))
    ).all()
    item_ids = [row.id for row in item_rows]

    # Nur in den gelöschten Rechnungen abgerechnete Ladevorgänge/Gebühren
    session_ids = {
        row.charging_session_id
        for row in item_rows
        if row.charging_session_id is not None
    }
    fee_ids = {
        row.monthly_base_fee_charge_id
        for row in item_rows
        if row.monthly_base_fee_charge_id is not None
    }

    if session_ids:
        still_used = db.scalars(
            select(InvoiceItem.charging_session_id).where(
                InvoiceItem.charging_session_id.in_(session_ids),
                InvoiceItem.invoice_id.not_in(invoice_ids),
            )
        ).all()
        session_ids -= set(still_used)

    if fee_ids:
        still_used = db.scalars(
            select(InvoiceItem.monthly_base_fee_charge_id).where(
                InvoiceItem.monthly_base_fee_charge_id.in_(fee_ids),
                InvoiceItem.invoice_id.not_in(invoice_ids),
            )
        ).all()
        fee_ids -= set(still_used)

    # verworfene Ladevorgänge aus dem gelöschten Zeitraum
    discarded_ids = set(
        db.scalars(
            select(ChargingSession.id).where(
                ChargingSession.start_time < boundary,
                ChargingSession.discarded_at.is_not(None),
            )
        ).all()
    )
    session_ids |= discarded_ids

    try:
        if item_ids:
            # Verweise aus anderen Positionen (Neuabrechnung, Storno)
            db.execute(
                update(InvoiceItem)
                .where(InvoiceItem.rebills_invoice_item_id.in_(item_ids))
                .values(rebills_invoice_item_id=None)
                .execution_options(synchronize_session=False)
            )
            db.execute(
                update(InvoiceItem)
                .where(InvoiceItem.reversed_invoice_item_id.in_(item_ids))
                .values(reversed_invoice_item_id=None)
                .execution_options(synchronize_session=False)
            )
            db.execute(
                delete(InvoiceItem)
                .where(InvoiceItem.id.in_(item_ids))
                .execution_options(synchronize_session=False)
            )

        # Gebühren, die noch auf eine gelöschte Rechnung zeigen
        db.execute(
            update(MonthlyBaseFeeCharge)
            .where(MonthlyBaseFeeCharge.invoice_id.in_(invoice_ids))
            .values(invoice_id=None)
            .execution_options(synchronize_session=False)
        )

        if fee_ids:
            db.execute(
                delete(MonthlyBaseFeeCharge)
                .where(MonthlyBaseFeeCharge.id.in_(fee_ids))
                .execution_options(synchronize_session=False)
            )

        if session_ids:
            db.execute(
                delete(ChargingSession)
                .where(ChargingSession.id.in_(session_ids))
                .execution_options(synchronize_session=False)
            )

        db.execute(
            delete(DeletedChargingSession)
            .where(DeletedChargingSession.start_time < boundary)
            .execution_options(synchronize_session=False)
        )

        db.execute(
            update(Invoice)
            .where(Invoice.id.in_(invoice_ids))
            .values(original_invoice_id=None)
            .execution_options(synchronize_session=False)
        )
        db.execute(
            delete(Invoice)
            .where(Invoice.id.in_(invoice_ids))
            .execution_options(synchronize_session=False)
        )

        if (
            settings.retention_purged_through_year is None
            or settings.retention_purged_through_year < year
        ):
            settings.retention_purged_through_year = year

        protocol = RetentionPurge(
            year=year,
            retention_years=retention_years,
            invoices=len(year_groups),
            cancellations=sum(
                group.cancellations for group in year_groups
            ),
            first_invoice_number=numbers[0] if numbers else None,
            last_invoice_number=numbers[-1] if numbers else None,
            pdf_files=0,
            charging_sessions=len(session_ids),
            base_fees=len(fee_ids),
            purged_by=purged_by,
        )
        db.add(protocol)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.expire_all()

    # PDFs erst nach erfolgreichem Löschen in der Datenbank entfernen
    removed, errors = _remove_pdf_files(db, pdf_paths, archive_root)

    protocol_entry = db.get(RetentionPurge, protocol.id)
    assert protocol_entry is not None
    protocol_entry.pdf_files = removed
    protocol_entry.pdf_errors = "\n".join(errors) or None
    db.commit()

    return PurgeResult(
        year=year,
        invoices=protocol_entry.invoices,
        cancellations=protocol_entry.cancellations,
        pdf_files=removed,
        charging_sessions=protocol_entry.charging_sessions,
        base_fees=protocol_entry.base_fees,
        pdf_errors=errors,
        protocol_id=protocol_entry.id,
    )
