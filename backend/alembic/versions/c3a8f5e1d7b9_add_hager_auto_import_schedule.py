"""add hager auto import schedule

Revision ID: c3a8f5e1d7b9
Revises: 9d4c1e7a2b58
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a8f5e1d7b9"
down_revision: Union[str, Sequence[str], None] = "9d4c1e7a2b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_interval_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_start_time",
            sa.String(length=5),
            nullable=False,
            server_default="03:00",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_last_started_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_last_finished_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_last_status",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_auto_import_last_message",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    for column in (
        "hager_auto_import_last_message",
        "hager_auto_import_last_status",
        "hager_auto_import_last_finished_at",
        "hager_auto_import_last_started_at",
        "hager_auto_import_start_time",
        "hager_auto_import_interval_hours",
        "hager_auto_import_enabled",
    ):
        op.drop_column("global_settings", column)
