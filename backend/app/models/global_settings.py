from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.utc import utc_now


class GlobalSettings(Base):
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        autoincrement=False,
    )

    app_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Witty-Accounting",
        server_default="Witty-Accounting",
    )

    monthly_base_fee_net: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("0.0000"),
        server_default="0.0000",
    )

    monthly_base_fee_vat_rate: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("19.00"),
        server_default="19.00",
    )

    invoice_payment_term_days: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
            default=0,
            server_default="0",
        )
    )

    invoice_issuer_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    invoice_issuer_address: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )

    invoice_tax_number: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    invoice_vat_id: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    invoice_bank_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    invoice_iban: Mapped[
        str | None
    ] = mapped_column(
        String(34),
        nullable=True,
    )

    invoice_bic: Mapped[
        str | None
    ] = mapped_column(
        String(11),
        nullable=True,
    )

    invoice_number_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="RE",
        server_default="RE",
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
