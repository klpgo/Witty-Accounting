from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base
from app.utils.utc import utc_now


class MonthlyBaseFeeCharge(Base):
    __tablename__ = "monthly_base_fee_charges"

    __table_args__ = (
        UniqueConstraint(
            "rfid_assignment_id",
            "fee_month",
            name=(
                "uq_monthly_base_fee_charges_"
                "assignment_month"
            ),
        ),
        Index(
            "ix_monthly_base_fee_charges_user_month",
            "user_id",
            "fee_month",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    rfid_card_id: Mapped[int] = mapped_column(
        ForeignKey(
            "rfid_cards.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    rfid_assignment_id: Mapped[int] = mapped_column(
        ForeignKey(
            "rfid_card_assignments.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    fee_month: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )

    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    invoiced: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "invoices.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    rfid_card = relationship(
        "RFIDCard",
    )

    rfid_assignment = relationship(
        "RFIDCardAssignment",
    )

    user = relationship(
        "User",
    )

    invoice = relationship(
        "Invoice",
        foreign_keys=[invoice_id],
    )

    invoice_items = relationship(
        "InvoiceItem",
        back_populates="monthly_base_fee_charge",
    )
