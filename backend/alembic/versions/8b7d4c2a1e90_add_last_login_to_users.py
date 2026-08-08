"""add last login to users

Revision ID: 8b7d4c2a1e90
Revises: 3a7d6e1f9b20
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b7d4c2a1e90"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "3a7d6e1f9b20"
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
        "users",
        sa.Column(
            "last_login",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "users",
        "last_login",
    )
