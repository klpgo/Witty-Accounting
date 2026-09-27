"""add e-mobility source fields

Revision ID: f4d1a8c6b2e0
Revises: e7b2d4a9c1f3
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d1a8c6b2e0"
down_revision: Union[str, Sequence[str], None] = "e7b2d4a9c1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "charging_sessions",
        sa.Column("wallbox_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_charging_sessions_wallbox_id",
        "charging_sessions",
        ["wallbox_id"],
    )
    op.add_column(
        "global_settings",
        sa.Column("hager_serial_number", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("global_settings", "hager_serial_number")
    op.drop_index(
        "ix_charging_sessions_wallbox_id",
        table_name="charging_sessions",
    )
    op.drop_column("charging_sessions", "wallbox_id")
