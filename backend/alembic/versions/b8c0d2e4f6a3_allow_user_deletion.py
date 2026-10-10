"""allow deleting users while keeping their invoices

- invoices.user_id wird optional (SET NULL): Rechnungen bleiben mit dem
  gespeicherten Empfänger im Archiv, wenn das Kundenkonto gelöscht wird
- invoice_items verweisen mit SET NULL auf Ladevorgänge und Grundgebühren,
  damit diese Abrechnungsdaten gelöscht werden können
- neue Tabelle deleted_charging_sessions: Merkmale gelöschter Ladevorgänge,
  damit Import und Hager-Abgleich sie nicht erneut anlegen

Revision ID: b8c0d2e4f6a3
Revises: a7b9d1f3c5e2
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c0d2e4f6a3"
down_revision: Union[str, Sequence[str], None] = "a7b9d1f3c5e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_foreign_key(
    *,
    table: str,
    old_name: str,
    new_name: str,
    column: str,
    referred_table: str,
    ondelete: str | None,
) -> None:
    op.drop_constraint(old_name, table, type_="foreignkey")
    op.create_foreign_key(
        new_name,
        table,
        referred_table,
        [column],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.drop_constraint("invoices_ibfk_1", "invoices", type_="foreignkey")
    op.alter_column(
        "invoices",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_invoices_user_id_users",
        "invoices",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _replace_foreign_key(
        table="invoice_items",
        old_name="invoice_items_ibfk_1",
        new_name="fk_invoice_items_charging_session_id",
        column="charging_session_id",
        referred_table="charging_sessions",
        ondelete="SET NULL",
    )
    _replace_foreign_key(
        table="invoice_items",
        old_name="fk_invoice_items_monthly_base_fee_charge",
        new_name="fk_invoice_items_monthly_base_fee_charge_id",
        column="monthly_base_fee_charge_id",
        referred_table="monthly_base_fee_charges",
        ondelete="SET NULL",
    )

    op.create_table(
        "deleted_charging_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hager_session_id", sa.String(100), nullable=True),
        sa.Column("import_hash", sa.String(64), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("wallbox_id", sa.String(64), nullable=True),
        sa.Column("station_id", sa.String(100), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_deleted_charging_sessions_hager_session_id",
        "deleted_charging_sessions",
        ["hager_session_id"],
    )
    op.create_index(
        "ix_deleted_charging_sessions_import_hash",
        "deleted_charging_sessions",
        ["import_hash"],
    )
    op.create_index(
        "ix_deleted_charging_sessions_start_time",
        "deleted_charging_sessions",
        ["start_time"],
    )


def downgrade() -> None:
    op.drop_table("deleted_charging_sessions")

    _replace_foreign_key(
        table="invoice_items",
        old_name="fk_invoice_items_monthly_base_fee_charge_id",
        new_name="fk_invoice_items_monthly_base_fee_charge",
        column="monthly_base_fee_charge_id",
        referred_table="monthly_base_fee_charges",
        ondelete=None,
    )
    _replace_foreign_key(
        table="invoice_items",
        old_name="fk_invoice_items_charging_session_id",
        new_name="invoice_items_ibfk_1",
        column="charging_session_id",
        referred_table="charging_sessions",
        ondelete=None,
    )

    # Schlägt fehl, solange Rechnungen gelöschter Benutzer vorhanden sind
    op.drop_constraint(
        "fk_invoices_user_id_users", "invoices", type_="foreignkey"
    )
    op.alter_column(
        "invoices",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "invoices_ibfk_1",
        "invoices",
        "users",
        ["user_id"],
        ["id"],
    )
