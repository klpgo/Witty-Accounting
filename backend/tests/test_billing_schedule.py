from datetime import date, datetime, time

import pytest

from app.services.billing_schedule import (
    latest_cutoff_on_or_before,
    next_cutoff_on_or_after,
    next_period,
    period_for_cutoff,
    run_at,
    validate_schedule,
)


@pytest.mark.parametrize(
    ("interval", "cutoff_day", "day", "expected"),
    [
        ("monthly", 0, date(2026, 2, 10), date(2026, 1, 31)),
        ("monthly", 0, date(2026, 2, 28), date(2026, 2, 28)),
        ("monthly", 15, date(2026, 3, 10), date(2026, 2, 15)),
        ("monthly", 15, date(2026, 3, 15), date(2026, 3, 15)),
        ("quarterly", 0, date(2026, 3, 30), date(2025, 12, 31)),
        ("quarterly", 0, date(2026, 3, 31), date(2026, 3, 31)),
        ("quarterly", 0, date(2026, 5, 1), date(2026, 3, 31)),
        ("weekly", 7, date(2026, 10, 10), date(2026, 10, 4)),
        ("weekly", 7, date(2026, 10, 11), date(2026, 10, 11)),
        ("weekly", 5, date(2026, 10, 11), date(2026, 10, 9)),
    ],
)
def test_latest_cutoff(interval, cutoff_day, day, expected) -> None:
    assert latest_cutoff_on_or_before(interval, cutoff_day, day) == expected


def test_next_cutoff() -> None:
    assert next_cutoff_on_or_after("monthly", 0, date(2026, 10, 10)) == date(
        2026, 10, 31
    )
    assert next_cutoff_on_or_after(
        "quarterly", 0, date(2026, 10, 10)
    ) == date(2026, 12, 31)
    assert next_cutoff_on_or_after("weekly", 7, date(2026, 10, 12)) == date(
        2026, 10, 18
    )


def test_periods_use_exclusive_end() -> None:
    monthly = period_for_cutoff("monthly", 0, date(2026, 2, 28))
    assert monthly.start == datetime(2026, 2, 1)
    assert monthly.end == datetime(2026, 3, 1)

    mid_month = period_for_cutoff("monthly", 15, date(2026, 3, 15))
    assert mid_month.start == datetime(2026, 2, 16)
    assert mid_month.end == datetime(2026, 3, 16)

    quarterly = period_for_cutoff("quarterly", 0, date(2026, 3, 31))
    assert quarterly.start == datetime(2026, 1, 1)
    assert quarterly.end == datetime(2026, 4, 1)

    weekly = period_for_cutoff("weekly", 7, date(2026, 10, 11))
    assert weekly.start == datetime(2026, 10, 5)
    assert weekly.end == datetime(2026, 10, 12)


def test_run_at_adds_grace_days() -> None:
    assert run_at(date(2026, 10, 31), 2, time(6, 0)) == datetime(
        2026, 11, 3, 6, 0
    )


def test_first_period_contains_activation_day() -> None:
    period = next_period(
        interval="monthly",
        cutoff_day=0,
        active_since=date(2026, 10, 10),
        last_period_end=None,
    )

    assert period.start == datetime(2026, 10, 1)
    assert period.end == datetime(2026, 11, 1)


def test_next_period_follows_last_run() -> None:
    period = next_period(
        interval="monthly",
        cutoff_day=0,
        active_since=date(2026, 1, 1),
        last_period_end=datetime(2026, 11, 1),
    )

    assert period.start == datetime(2026, 11, 1)
    assert period.end == datetime(2026, 12, 1)


def test_interval_change_does_not_overlap_last_run() -> None:
    # bisher wöchentlich bis So 11.10., jetzt monatlich zum Monatsletzten
    period = next_period(
        interval="monthly",
        cutoff_day=0,
        active_since=date(2026, 1, 1),
        last_period_end=datetime(2026, 10, 12),
    )

    assert period.start == datetime(2026, 10, 12)
    assert period.end == datetime(2026, 11, 1)


def test_reactivation_does_not_bill_the_gap() -> None:
    period = next_period(
        interval="monthly",
        cutoff_day=0,
        active_since=date(2026, 10, 10),
        last_period_end=datetime(2026, 6, 1),
    )

    assert period.start == datetime(2026, 10, 1)
    assert period.end == datetime(2026, 11, 1)


@pytest.mark.parametrize(
    ("interval", "cutoff_day"),
    [("weekly", 0), ("weekly", 8), ("monthly", 29), ("yearly", 1)],
)
def test_invalid_schedules_are_rejected(interval, cutoff_day) -> None:
    with pytest.raises(ValueError):
        validate_schedule(interval, cutoff_day)
