"""
Zeitplan für den automatischen Hager-Abruf.

Regel: "alle N Stunden, beginnend um HH:MM" (Ortszeit Europe/Berlin),
N zwischen 1 und 24.

Jeder Tag beginnt beim Startzeitpunkt neu. Von dort aus liegt alle N
Stunden ein Abrufzeitpunkt, bis der Startzeitpunkt des Folgetags
erreicht ist. Beispiel N=5, Start 03:00: 03, 08, 13, 18, 23 Uhr, dann
wieder 03 Uhr. So gibt es mindestens einen Abruf pro Tag, und der
Startzeitpunkt bleibt fest – auch wenn N kein Teiler von 24 ist und
über Sommer-/Winterzeitwechsel hinweg (gerechnet wird nach der Wanduhr).

Ein Abruf ist fällig, wenn der letzte Lauf vor dem jüngsten bereits
erreichten Abrufzeitpunkt gestartet wurde (oder noch nie lief). Dadurch
werden verpasste Läufe – etwa nach einem Neustart – einmal nachgeholt.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24
_START_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_start_time(value: str) -> time:
    match = _START_TIME_PATTERN.match(value or "")

    if match is None:
        raise ValueError(
            "Die Startzeit muss im Format HH:MM angegeben werden."
        )

    return time(int(match.group(1)), int(match.group(2)))


def validate_interval(hours: int) -> int:
    if not MIN_INTERVAL_HOURS <= hours <= MAX_INTERVAL_HOURS:
        raise ValueError(
            "Das Intervall muss zwischen 1 und 24 Stunden liegen."
        )

    return hours


def _as_utc(value: datetime) -> datetime:
    """Naive Werte gelten als UTC (so speichert Witty Zeitpunkte)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def slots_for_day(day: date, start: time, interval_hours: int) -> list[datetime]:
    """
    Abrufzeitpunkte (UTC) des Tages, der am `day` um `start` beginnt.

    Gerechnet wird nach der Wanduhr: Start + 0, N, 2N, … Stunden, solange
    weniger als 24 Stunden erreicht sind. An Tagen der Zeitumstellung
    bleiben die Uhrzeiten damit gleich (z. B. immer 03, 09, 15, 21 Uhr).
    """
    validate_interval(interval_hours)
    first_local = datetime.combine(day, start)

    return [
        (first_local + timedelta(hours=offset))
        .replace(tzinfo=LOCAL_TIMEZONE)
        .astimezone(UTC)
        for offset in range(0, 24, interval_hours)
    ]


def latest_slot(now: datetime, start: time, interval_hours: int) -> datetime:
    """Jüngster Abrufzeitpunkt, der zum Zeitpunkt `now` erreicht ist."""
    now_utc = _as_utc(now)
    today = now_utc.astimezone(LOCAL_TIMEZONE).date()

    for day in (today, today - timedelta(days=1), today - timedelta(days=2)):
        reached = [
            slot
            for slot in slots_for_day(day, start, interval_hours)
            if slot <= now_utc
        ]

        if reached:
            return max(reached)

    raise RuntimeError("Kein Abrufzeitpunkt gefunden.")  # pragma: no cover


def next_slot(now: datetime, start: time, interval_hours: int) -> datetime:
    """Nächster Abrufzeitpunkt nach `now`."""
    now_utc = _as_utc(now)
    today = now_utc.astimezone(LOCAL_TIMEZONE).date()

    for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
        for slot in slots_for_day(day, start, interval_hours):
            if slot > now_utc:
                return slot

    raise RuntimeError("Kein Abrufzeitpunkt gefunden.")  # pragma: no cover


def is_due(
    now: datetime,
    last_started_at: datetime | None,
    start: time,
    interval_hours: int,
) -> bool:
    if last_started_at is None:
        return True

    return _as_utc(last_started_at) < latest_slot(now, start, interval_hours)
