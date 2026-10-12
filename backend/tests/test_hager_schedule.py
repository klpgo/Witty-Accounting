from datetime import UTC, date, datetime, time

import pytest

from app.services.hager_schedule import (
    LOCAL_TIMEZONE,
    is_due,
    latest_slot,
    next_slot,
    parse_start_time,
    slots_for_day,
    validate_interval,
)


START = time(3, 0)


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=LOCAL_TIMEZONE)


def local_times(slots: list[datetime]) -> list[str]:
    return [s.astimezone(LOCAL_TIMEZONE).strftime("%H:%M") for s in slots]


def naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        (24, ["03:00"]),
        (6, ["03:00", "09:00", "15:00", "21:00"]),
        (5, ["03:00", "08:00", "13:00", "18:00", "23:00"]),
        (7, ["03:00", "10:00", "17:00", "00:00"]),
    ],
)
def test_slots_for_day(interval: int, expected: list[str]) -> None:
    assert local_times(slots_for_day(date(2026, 9, 24), START, interval)) == expected


def test_hourly_gives_24_slots() -> None:
    assert len(slots_for_day(date(2026, 9, 24), START, 1)) == 24


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])
def test_wall_clock_times_stay_fixed_on_dst_change(day: date) -> None:
    assert local_times(slots_for_day(day, START, 6)) == [
        "03:00",
        "09:00",
        "15:00",
        "21:00",
    ]


def test_latest_and_next_slot() -> None:
    now = local(2026, 9, 24, 14, 30)

    assert latest_slot(now, START, 6) == local(2026, 9, 24, 9, 0)
    assert next_slot(now, START, 6) == local(2026, 9, 24, 15, 0)


def test_before_start_time_uses_previous_day() -> None:
    now = local(2026, 9, 24, 1, 0)

    assert latest_slot(now, START, 24) == local(2026, 9, 23, 3, 0)
    assert next_slot(now, START, 24) == local(2026, 9, 24, 3, 0)


def test_start_in_evening_crosses_midnight() -> None:
    now = local(2026, 9, 25, 1, 0)

    assert latest_slot(now, time(22, 0), 6) == local(2026, 9, 24, 22, 0)
    assert next_slot(now, time(22, 0), 6) == local(2026, 9, 25, 4, 0)


def test_is_due_without_previous_run() -> None:
    assert is_due(local(2026, 9, 24, 14, 30), None, START, 6)


def test_is_due_only_after_next_slot() -> None:
    last = naive_utc(local(2026, 9, 24, 9, 0, 5))

    assert not is_due(local(2026, 9, 24, 14, 59), last, START, 6)
    assert is_due(local(2026, 9, 24, 15, 0), last, START, 6)


def test_missed_run_is_caught_up_once() -> None:
    # letzter Lauf gestern 03:00, Container war heute um 03:00 aus
    last = naive_utc(local(2026, 9, 23, 3, 0, 5))
    now = local(2026, 9, 24, 7, 12)

    assert is_due(now, last, START, 24)
    assert not is_due(now, naive_utc(now), START, 24)


@pytest.mark.parametrize("value", ["3:00", "24:00", "03:60", "abc", ""])
def test_parse_start_time_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_start_time(value)


def test_parse_start_time() -> None:
    assert parse_start_time("07:45") == time(7, 45)


@pytest.mark.parametrize("hours", [0, 25])
def test_validate_interval(hours: int) -> None:
    with pytest.raises(ValueError):
        validate_interval(hours)
