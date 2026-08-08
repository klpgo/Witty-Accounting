from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from app.utils.utc import utc_now

class RFIDCard(Base):

    __tablename__ = "rfid_cards"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    rfid_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
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

    assignments = relationship(
        "RFIDCardAssignment",
        back_populates="rfid_card",
        order_by=(
            "RFIDCardAssignment.valid_from"
        ),
    )
