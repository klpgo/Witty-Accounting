from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Numeric, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from app.utils.utc import utc_now


class ChargingSession(Base):

    __tablename__ = "charging_sessions"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    # ID aus der Hager Flow API
    hager_session_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=True
    )

    # Identifikation der Witty Ladestation
    station_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # Hash zur Dublettenerkennung bei XLSX-/CSV-Import
    import_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True
    )

    # Quelle des Datensatzes (xlsx, api, csv ...)
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="xlsx"
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    # Zuordnung zur RFID-Karte
    rfid_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("rfid_cards.id"),
        nullable=True
    )

    energy_total_kwh: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    energy_pv_kwh: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    cost_grid_net: Mapped[float | None] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )

    cost_pv_net: Mapped[float | None] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )

    vat_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True
    )

    invoiced: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    invoice_id: Mapped[int | None] = mapped_column(
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now
    )

    rfid_card = relationship(
        "RFIDCard"
    )
