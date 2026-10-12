from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.utc import utc_now


# Status eines Abrechnungslaufs
RUN_WAITING_FOR_DATA = "waiting_for_data"
RUN_IN_REVIEW = "in_review"
RUN_COMPLETED = "completed"


class BillingRun(Base):
    """
    Ein Lauf der automatischen Abrechnung: ein Leistungszeitraum, für den
    Rechnungsentwürfe erstellt, zur Prüfung versandt und nach Ablauf der
    Prüffrist finalisiert werden.

    Der Leistungszeitraum ist eindeutig (period_start), damit ein Zeitraum
    auch bei Neustarts oder parallelen Prüfungen nur einmal abgerechnet
    wird. Zeitpunkte des Leistungszeitraums sind Ortszeit, das Ende ist
    exklusiv (wie bei Invoice.service_period_end).
    """

    __tablename__ = "billing_runs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=True,
    )

    period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    # Stichtag (letzter Tag des Leistungszeitraums) und Intervall zum
    # Zeitpunkt des Laufs
    cutoff_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    interval: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RUN_WAITING_FOR_DATA,
        server_default=RUN_WAITING_FOR_DATA,
    )

    # Ende der Prüffrist der in diesem Lauf erstellten Entwürfe
    review_due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    drafts_created: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Übersprungene Kunden und Fehler als JSON-Liste
    # [{"user_id": 1, "name": "…", "reason": "…", "message": "…"}]
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Einmaliger Hinweis an den Rechnungssteller, dass Ladedaten fehlen
    waiting_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    drafts_created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
