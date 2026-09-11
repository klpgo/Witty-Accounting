from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.utc import utc_now


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
    )

    document_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="invoice",
        server_default="invoice",
    )

    cancellation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    issuer_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    issuer_address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    issuer_tax_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    issuer_vat_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    issuer_bank_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    issuer_iban: Mapped[
        str | None
    ] = mapped_column(
        String(34),
        nullable=True,
    )

    issuer_bic: Mapped[
        str | None
    ] = mapped_column(
        String(11),
        nullable=True,
    )

    issuer_phone: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    recipient_address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    issue_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    service_period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    service_period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
        server_default="EUR",
    )

    total_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    total_gross: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
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

    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    user = relationship(
        "User",
        back_populates="invoices",
    )

    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.position_number",
    )

    pdf_storage_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    pdf_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    pdf_size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    pdf_created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    pdf_exported_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    pdf_exported_by_user_id: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    pdf_export_remote_path: Mapped[
        str | None
    ] = mapped_column(
        String(1200),
        nullable=True,
    )

    original_invoice: Mapped[
        "Invoice | None"
    ] = relationship(
        "Invoice",
        remote_side="Invoice.id",
        foreign_keys="Invoice.original_invoice_id",
        back_populates="cancellation_invoice",
    )

    cancellation_invoice: Mapped[
        "Invoice | None"
    ] = relationship(
        "Invoice",
        foreign_keys="Invoice.original_invoice_id",
        back_populates="original_invoice",
        uselist=False,
    )

    original_invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "invoices.id",
            ondelete="RESTRICT",
        ),
        unique=True,
        nullable=True,
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id",
            "position_number",
            name="uq_invoice_items_invoice_position",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey(
            "invoices.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="charging_session",
        server_default="charging_session",
    )

    monthly_base_fee_charge_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "monthly_base_fee_charges.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    charging_session_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "charging_sessions.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    reversed_invoice_item_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "invoice_items.id",
            ondelete="RESTRICT",
        ),
        unique=True,
        nullable=True,
    )

    rebills_invoice_item_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "invoice_items.id",
            ondelete="RESTRICT",
        ),
        unique=True,
        nullable=True,
    )

    position_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    session_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
    )

    session_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
    )

    station_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
    )

    energy_total_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )

    energy_grid_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )

    energy_pv_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )

    grid_price_net: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    pv_price_net: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    cost_grid_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )

    cost_pv_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )

    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )

    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    invoice = relationship(
        "Invoice",
        back_populates="items",
    )

    charging_session = relationship(
        "ChargingSession",
        back_populates="invoice_items",
    )

    monthly_base_fee_charge = relationship(
        "MonthlyBaseFeeCharge",
        back_populates="invoice_items",
    )

    reversed_invoice_item: Mapped[
        "InvoiceItem | None"
    ] = relationship(
        "InvoiceItem",
        remote_side="InvoiceItem.id",
        foreign_keys=[reversed_invoice_item_id],
        back_populates="reversal_item",
    )

    rebills_invoice_item: Mapped[
        "InvoiceItem | None"
    ] = relationship(
        "InvoiceItem",
        remote_side="InvoiceItem.id",
        foreign_keys=[rebills_invoice_item_id],
        back_populates="rebilled_by_item",
    )

    rebilled_by_item: Mapped[
        "InvoiceItem | None"
    ] = relationship(
        "InvoiceItem",
        foreign_keys=(
            "InvoiceItem.rebills_invoice_item_id"
        ),
        back_populates="rebills_invoice_item",
        uselist=False,
    )

    reversal_item: Mapped[
        "InvoiceItem | None"
    ] = relationship(
        "InvoiceItem",
        foreign_keys=(
            "InvoiceItem.reversed_invoice_item_id"
        ),
        back_populates="reversed_invoice_item",
        uselist=False,
    )
