"""add invoice retention and purge protocol

- global_settings.invoice_retention_years (Standard 10)
- global_settings.retention_purged_through_year
- neue Tabelle retention_purges (Löschprotokoll)

Revision ID: c9d1e3f5a7b4
Revises: b8c0d2e4f6a3
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e3f5a7b4"
down_revision: Union[str, Sequence[str], None] = "b8c0d2e4f6a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_retention_years",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "retention_purged_through_year",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_table(
        "retention_purges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("retention_years", sa.Integer(), nullable=False),
        sa.Column("invoices", sa.Integer(), nullable=False),
        sa.Column("cancellations", sa.Integer(), nullable=False),
        sa.Column("first_invoice_number", sa.String(50), nullable=True),
        sa.Column("last_invoice_number", sa.String(50), nullable=True),
        sa.Column("pdf_files", sa.Integer(), nullable=False),
        sa.Column("charging_sessions", sa.Integer(), nullable=False),
        sa.Column("base_fees", sa.Integer(), nullable=False),
        sa.Column("pdf_errors", sa.Text(), nullable=True),
        sa.Column("purged_by", sa.String(255), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_retention_purges_year",
        "retention_purges",
        ["year"],
    )


def downgrade() -> None:
    op.drop_table("retention_purges")
    op.drop_column("global_settings", "retention_purged_through_year")
    op.drop_column("global_settings", "invoice_retention_years")
