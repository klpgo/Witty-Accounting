"""share base fee VAT rate with postage

Revision ID: 3a7d6e1f9b20
Revises: c6e9340a21bd
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3a7d6e1f9b20"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "c6e9340a21bd"
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
    op.drop_column(
        "global_settings",
        "postal_delivery_fee_vat_rate",
    )


def downgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "postal_delivery_fee_vat_rate",
            sa.Numeric(precision=5, scale=2),
            server_default="19.00",
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE global_settings "
            "SET postal_delivery_fee_vat_rate = "
            "monthly_base_fee_vat_rate"
        )
    )
