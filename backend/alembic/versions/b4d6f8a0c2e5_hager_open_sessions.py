"""track charging sessions that are not finished yet in the Hager Cloud

Revision ID: b4d6f8a0c2e5
Revises: a3b5c7d9e1f4
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d6f8a0c2e5"
down_revision: Union[str, Sequence[str], None] = "a3b5c7d9e1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "charging_sessions",
        sa.Column("hager_status", sa.String(30), nullable=True),
    )
    op.add_column(
        "charging_sessions",
        sa.Column("hager_state", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_charging_sessions_hager_state",
        "charging_sessions",
        ["hager_state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_charging_sessions_hager_state",
        table_name="charging_sessions",
    )
    op.drop_column("charging_sessions", "hager_state")
    op.drop_column("charging_sessions", "hager_status")
