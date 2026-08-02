from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from app.utils.utc import utc_now


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    salutation: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    invoice_delivery_email: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    invoice_delivery_post: Mapped[bool] = mapped_column(
        Boolean,
        default=False
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

    rfid_assignments = relationship(
        "RFIDCardAssignment",
        back_populates="user",
        order_by=(
            "RFIDCardAssignment.valid_from"
        ),
    )

    invoices = relationship(
        "Invoice",
        back_populates="user",
    )

    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
