"""add invoice business settings

Revision ID: b2689e6b406e
Revises: 36095c9651c1
Create Date: 2026-07-31 09:58:02.215586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2689e6b406e'
down_revision: Union[str, Sequence[str], None] = '36095c9651c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_issuer_name",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_issuer_address",
            sa.String(length=500),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_tax_number",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_vat_id",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_bank_name",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_iban",
            sa.String(length=34),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_bic",
            sa.String(length=11),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_number_prefix",
            sa.String(length=20),
            server_default=sa.text("'RE'"),
            nullable=False,
        ),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "issuer_bank_name",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "issuer_iban",
            sa.String(length=34),
            nullable=True,
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "issuer_bic",
            sa.String(length=11),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "invoices",
        "issuer_bic",
    )
    op.drop_column(
        "invoices",
        "issuer_iban",
    )
    op.drop_column(
        "invoices",
        "issuer_bank_name",
    )

    op.drop_column(
        "global_settings",
        "invoice_number_prefix",
    )
    op.drop_column(
        "global_settings",
        "invoice_bic",
    )
    op.drop_column(
        "global_settings",
        "invoice_iban",
    )
    op.drop_column(
        "global_settings",
        "invoice_bank_name",
    )
    op.drop_column(
        "global_settings",
        "invoice_vat_id",
    )
    op.drop_column(
        "global_settings",
        "invoice_tax_number",
    )
    op.drop_column(
        "global_settings",
        "invoice_issuer_address",
    )
    op.drop_column(
        "global_settings",
        "invoice_issuer_name",
    )
