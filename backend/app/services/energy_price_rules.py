"""
Regeln für das Anlegen und Ändern von Energiepreisen.

Ein Energiepreis darf nur ab einem Zeitpunkt gelten, ab dem es keine Rechnung
mehr gibt – andernfalls würden bereits abgerechnete (oder in Entwürfen
bepreiste) Ladevorgänge rückwirkend einen anderen Preis erhalten. Maßgeblich
ist das Ende des spätesten Leistungszeitraums aller Rechnungen, Entwürfe
eingeschlossen (das Ende ist exklusiv).
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.invoice import Invoice


class EnergyPriceLockedError(ValueError):
    """Der Zeitpunkt liegt in einem bereits abgerechneten Zeitraum."""


def editable_from(db: Session) -> datetime | None:
    """Frühester Zeitpunkt, ab dem Energiepreise gesetzt werden dürfen;
    None, solange es keine Rechnung gibt."""
    return db.scalar(select(func.max(Invoice.service_period_end)))


def day_start(value: date) -> datetime:
    return datetime.combine(value, time.min)


def ensure_editable(db: Session, *moments: datetime) -> None:
    """Prüft, dass alle Zeitpunkte nicht vor dem Abrechnungsstand liegen."""
    boundary = editable_from(db)

    if boundary is None:
        return

    for moment in moments:
        if moment < boundary:
            raise EnergyPriceLockedError(
                "Energy prices can only be set from "
                f"{boundary:%Y-%m-%d} onwards, because invoices exist up to "
                "this date."
            )
