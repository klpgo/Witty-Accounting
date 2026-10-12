"""optional VAT (small business, § 19 UStG)

- global_settings.vat_enabled (Standard: an)
- global_settings.vat_exemption_note (Hinweis auf der Rechnung ohne USt)
- invoices.vat_exempt, invoices.vat_exemption_note (je Rechnung festgehalten)

Revision ID: a3b5c7d9e1f4
Revises: f2a4c6e8b0d3
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b5c7d9e1f4"
down_revision: Union[str, Sequence[str], None] = "f2a4c6e8b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_NOTE = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "vat_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column("vat_exemption_note", sa.String(500), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE global_settings SET vat_exemption_note = :note"
        ).bindparams(note=DEFAULT_NOTE)
    )
    op.add_column(
        "invoices",
        sa.Column(
            "vat_exempt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "invoices",
        sa.Column("vat_exemption_note", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "vat_exemption_note")
    op.drop_column("invoices", "vat_exempt")
    op.drop_column("global_settings", "vat_exemption_note")
    op.drop_column("global_settings", "vat_enabled")
