"""add billing start date

Revision ID: d91e6f4a2b73
Revises: b4d8f2a73c19
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d91e6f4a2b73"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "b4d8f2a73c19"
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
            "billing_start_date",
            sa.Date(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "billing_start_date",
    )
