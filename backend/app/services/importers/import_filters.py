"""
Gemeinsame Regeln, welche Ladevorgänge beim Import übernommen werden –
für alle Importwege (Hager Cloud, JSON, XLSX).

- Ladevorgänge vor dem Abrechnungsbeginn werden nie importiert, ebenso
  Ladevorgänge aus Jahren, deren Daten nach Ablauf der Aufbewahrungsfrist
  gelöscht wurden.
- Optional (Einstellung): Ladevorgänge ohne Energie (0 kWh) werden
  nicht importiert, z. B. abgebrochene oder nicht autorisierte Vorgänge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings


BEFORE_BILLING_START = "before_billing_start"
EMPTY = "empty"


@dataclass(frozen=True)
class ImportFilters:
    not_before: date | None = None
    skip_empty: bool = False


def load_import_filters(db: Session) -> ImportFilters:
    settings = db.get(GlobalSettings, 1)

    if settings is None:
        return ImportFilters()

    not_before = settings.billing_start_date
    purged_through = getattr(settings, "retention_purged_through_year", None)

    if purged_through is not None:
        purged_boundary = date(purged_through + 1, 1, 1)

        if not_before is None or not_before < purged_boundary:
            not_before = purged_boundary

    return ImportFilters(
        not_before=not_before,
        skip_empty=bool(settings.import_skip_empty_sessions),
    )


def exclusion_reason(
    filters: ImportFilters,
    start_time: datetime,
    energy_total_kwh: float,
) -> str | None:
    """Grund, warum ein Ladevorgang nicht importiert wird, sonst None."""
    if filters.not_before is not None and start_time.date() < filters.not_before:
        return BEFORE_BILLING_START

    if filters.skip_empty and not energy_total_kwh:
        return EMPTY

    return None


class ExclusionCounter:
    def __init__(self) -> None:
        self.before_billing_start = 0
        self.empty = 0

    def add(self, reason: str) -> None:
        if reason == BEFORE_BILLING_START:
            self.before_billing_start += 1
        elif reason == EMPTY:
            self.empty += 1

    def as_result(self) -> dict[str, int]:
        return {
            "skipped_before_billing_start": self.before_billing_start,
            "skipped_empty": self.empty,
        }
