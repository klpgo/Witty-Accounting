"""add postal delivery fee

Revision ID: c6e9340a21bd
Revises: a8c1d9e4f2b7
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6e9340a21bd"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "a8c1d9e4f2b7"
branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None
depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "postal_delivery_fee_net",
            sa.Numeric(precision=12, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "postal_delivery_fee_vat_rate",
            sa.Numeric(precision=5, scale=2),
            server_default="19.00",
            nullable=False,
        ),
    )

    # Die bisher erlaubte Kombination E-Mail und Post
    # wird auf die kostenfreie E-Mail-Zustellung abgebildet.
    op.execute(
        sa.text(
            "UPDATE users "
            "SET invoice_delivery_post = 0 "
            "WHERE invoice_delivery_email = 1 "
            "AND invoice_delivery_post = 1"
        )
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "postal_delivery_fee_vat_rate",
    )
    op.drop_column(
        "global_settings",
        "postal_delivery_fee_net",
    )
