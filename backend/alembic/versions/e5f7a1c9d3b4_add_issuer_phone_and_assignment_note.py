"""add issuer phone and rfid assignment note

Revision ID: e5f7a1c9d3b4
Revises: d71c9a4e6b20
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f7a1c9d3b4"
down_revision: Union[str, Sequence[str], None] = "d71c9a4e6b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_issuer_phone",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "issuer_phone",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "rfid_card_assignments",
        sa.Column(
            "note",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "rfid_card_assignments",
        "note",
    )

    op.drop_column(
        "invoices",
        "issuer_phone",
    )

    op.drop_column(
        "global_settings",
        "invoice_issuer_phone",
    )
