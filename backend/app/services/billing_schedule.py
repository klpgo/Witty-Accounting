"""
Zeitplan der automatischen Abrechnung.

Ein Leistungszeitraum endet an einem Stichtag (einschließlich) und beginnt
am Tag nach dem vorherigen Stichtag:

- wöchentlich: Stichtag ist ein Wochentag (1 = Montag … 7 = Sonntag),
- monatlich: Tag 1–28 des Monats oder der Monatsletzte (0),
- vierteljährlich: wie monatlich, aber nur im letzten Monat eines
  Kalenderquartals (März, Juni, September, Dezember).

Gespeichert wird der Zeitraum wie bei manuellen Entwürfen als Ortszeit mit
exklusivem Ende: Stichtag 31.10. → 01.10. 00:00 bis 01.11. 00:00.

Die Entwürfe werden `grace_days` Tage nach dem Stichtag zur eingestellten
Uhrzeit erstellt, damit nachträglich übertragene Ladevorgänge noch
berücksichtigt werden.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

INTERVAL_WEEKLY = "weekly"
INTERVAL_MONTHLY = "monthly"
INTERVAL_QUARTERLY = "quarterly"
INTERVALS = (INTERVAL_WEEKLY, INTERVAL_MONTHLY, INTERVAL_QUARTERLY)

LAST_DAY_OF_MONTH = 0
MAX_MONTH_DAY = 28

MIN_GRACE_DAYS = 0
MAX_GRACE_DAYS = 31
MIN_REVIEW_DAYS = 1
MAX_REVIEW_DAYS = 60


@dataclass(frozen=True)
class BillingPeriod:
    cutoff: date
    # Ortszeit, Ende exklusiv
    start: datetime
    end: datetime


def validate_schedule(interval: str, cutoff_day: int) -> None:
    if interval not in INTERVALS:
        raise ValueError(
            "The interval must be weekly, monthly or quarterly."
        )

    if interval == INTERVAL_WEEKLY:
        if not 1 <= cutoff_day <= 7:
            raise ValueError(
                "For weekly billing the cutoff day must be a weekday "
                "between 1 (Monday) and 7 (Sunday)."
            )
    elif not LAST_DAY_OF_MONTH <= cutoff_day <= MAX_MONTH_DAY:
        raise ValueError(
            "The cutoff day must be between 1 and 28, or 0 for the last day "
            "of the month."
        )


def _month_cutoff(year: int, month: int, cutoff_day: int) -> date:
    last_day = monthrange(year, month)[1]

    if cutoff_day == LAST_DAY_OF_MONTH:
        return date(year, month, last_day)

    return date(year, month, min(cutoff_day, last_day))


def _shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + months

    return index // 12, index % 12 + 1


def latest_cutoff_on_or_before(
    interval: str,
    cutoff_day: int,
    day: date,
) -> date:
    """Jüngster Stichtag am oder vor `day`."""
    validate_schedule(interval, cutoff_day)

    if interval == INTERVAL_WEEKLY:
        return day - timedelta(days=(day.isoweekday() - cutoff_day) % 7)

    if interval == INTERVAL_MONTHLY:
        year, month = day.year, day.month
        step = 1
    else:
        # letzter Monat des Quartals, in dem `day` liegt
        year, month = day.year, ((day.month - 1) // 3 + 1) * 3
        step = 3

    cutoff = _month_cutoff(year, month, cutoff_day)

    while cutoff > day:
        year, month = _shift_month(year, month, -step)
        cutoff = _month_cutoff(year, month, cutoff_day)

    return cutoff


def previous_cutoff(interval: str, cutoff_day: int, cutoff: date) -> date:
    return latest_cutoff_on_or_before(
        interval,
        cutoff_day,
        cutoff - timedelta(days=1),
    )


def next_cutoff_on_or_after(
    interval: str,
    cutoff_day: int,
    day: date,
) -> date:
    """Frühester Stichtag am oder nach `day`."""
    latest = latest_cutoff_on_or_before(interval, cutoff_day, day)

    if latest == day:
        return latest

    if interval == INTERVAL_WEEKLY:
        return latest + timedelta(days=7)

    step = 1 if interval == INTERVAL_MONTHLY else 3
    year, month = _shift_month(latest.year, latest.month, step)

    return _month_cutoff(year, month, cutoff_day)


def period_for_cutoff(
    interval: str,
    cutoff_day: int,
    cutoff: date,
) -> BillingPeriod:
    start = previous_cutoff(interval, cutoff_day, cutoff) + timedelta(days=1)

    return BillingPeriod(
        cutoff=cutoff,
        start=datetime.combine(start, time.min),
        end=datetime.combine(cutoff + timedelta(days=1), time.min),
    )


def run_at(cutoff: date, grace_days: int, run_time: time) -> datetime:
    """Ortszeit, zu der die Entwürfe für den Stichtag erstellt werden."""
    return datetime.combine(
        cutoff + timedelta(days=1 + grace_days),
        run_time,
    )


def next_period(
    *,
    interval: str,
    cutoff_day: int,
    active_since: date,
    last_period_end: datetime | None,
) -> BillingPeriod:
    """
    Nächster abzurechnender Leistungszeitraum.

    Ohne bisherigen Lauf ist es der Zeitraum mit dem ersten Stichtag am oder
    nach dem Einschalten. Danach schließt der Zeitraum an den letzten Lauf
    an. Liegt der letzte Lauf vor dem (erneuten) Einschalten, beginnt der
    Zeitraum regulär; die Lücke bleibt der manuellen Abrechnung überlassen.
    Nach einem Wechsel des Intervalls beginnt der erste Zeitraum direkt nach
    dem letzten Lauf, damit sich Zeiträume nicht überschneiden.
    """
    earliest = active_since

    if last_period_end is not None:
        earliest = max(earliest, last_period_end.date())

    cutoff = next_cutoff_on_or_after(interval, cutoff_day, earliest)
    period = period_for_cutoff(interval, cutoff_day, cutoff)

    if last_period_end is not None and last_period_end > period.start:
        period = BillingPeriod(
            cutoff=period.cutoff,
            start=last_period_end,
            end=period.end,
        )

    return period
