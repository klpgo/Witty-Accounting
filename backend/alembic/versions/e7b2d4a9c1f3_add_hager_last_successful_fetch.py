"""add hager last successful fetch

Revision ID: e7b2d4a9c1f3
Revises: c3a8f5e1d7b9
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b2d4a9c1f3"
down_revision: Union[str, Sequence[str], None] = "c3a8f5e1d7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_last_successful_fetch_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "hager_last_successful_fetch_at",
    )
