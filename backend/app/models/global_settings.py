from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    Boolean,
    Text,
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

    postal_delivery_fee_net: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("0.0000"),
        server_default="0.0000",
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

    invoice_pdf_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="standard",
        server_default="standard",
    )

    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    dashboard_note: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    password_min_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=8,
        server_default="8",
    )

    password_require_uppercase: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    password_require_lowercase: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    password_require_digit: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    password_require_special: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    frontend_base_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        default="http://localhost:5173",
        server_default="http://localhost:5173",
    )

    password_reset_token_expire_minutes: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        server_default="60",
    )

    smtp_use_database_settings: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    mail_sending_enabled: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    smtp_host: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    smtp_port: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    smtp_timeout_seconds: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(8, 2),
        nullable=True,
    )

    smtp_starttls: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    smtp_username: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    smtp_password_encrypted: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    mail_from_address: Mapped[
        str | None
    ] = mapped_column(
        String(320),
        nullable=True,
    )

    mail_from_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
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
