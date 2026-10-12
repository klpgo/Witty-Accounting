from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.utc import utc_now


class RetentionPurge(Base):
    """
    Löschprotokoll: ein Eintrag je gelöschtem Jahr nach Ablauf der
    Aufbewahrungsfrist. Enthält keine Kundendaten, nur Umfang,
    Nummernbereich, Zeitpunkt und den ausführenden Administrator.
    """

    __tablename__ = "retention_purges"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    retention_years: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    invoices: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    cancellations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    first_invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    last_invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    pdf_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    charging_sessions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    base_fees: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # PDF-Dateien, die nicht entfernt werden konnten (relative Pfade)
    pdf_errors: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    purged_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    purged_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )
