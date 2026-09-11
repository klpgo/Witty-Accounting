from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base
from app.utils.utc import utc_now


class RFIDCardAssignment(Base):
    __tablename__ = "rfid_card_assignments"

    __table_args__ = (
        UniqueConstraint(
            "rfid_card_id",
            "valid_from",
            name=(
                "uq_rfid_card_assignments_"
                "card_valid_from"
            ),
        ),
        Index(
            "ix_rfid_card_assignments_card_period",
            "rfid_card_id",
            "valid_from",
            "valid_to",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    rfid_card_id: Mapped[int] = mapped_column(
        ForeignKey("rfid_cards.id"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    valid_from: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    valid_to: Mapped[datetime | None] = (
        mapped_column(
            DateTime,
            nullable=True,
        )
    )

    note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    rfid_card = relationship(
        "RFIDCard",
        back_populates="assignments",
    )

    user = relationship(
        "User",
        back_populates="rfid_assignments",
    )

    charging_sessions = relationship(
        "ChargingSession",
        back_populates="rfid_assignment",
    )
