"""add session discard and import filter

Revision ID: a9e3c7b5d2f1
Revises: f4d1a8c6b2e0
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9e3c7b5d2f1"
down_revision: Union[str, Sequence[str], None] = "f4d1a8c6b2e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "charging_sessions",
        sa.Column("discarded_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_charging_sessions_discarded_at",
        "charging_sessions",
        ["discarded_at"],
    )
    op.add_column(
        "charging_sessions",
        sa.Column("discarded_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_charging_sessions_discarded_by_user_id_users",
        "charging_sessions",
        "users",
        ["discarded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "charging_sessions",
        sa.Column("discard_reason", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "import_skip_empty_sessions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("global_settings", "import_skip_empty_sessions")
    op.drop_column("charging_sessions", "discard_reason")
    op.drop_constraint(
        "fk_charging_sessions_discarded_by_user_id_users",
        "charging_sessions",
        type_="foreignkey",
    )
    op.drop_column("charging_sessions", "discarded_by_user_id")
    op.drop_index(
        "ix_charging_sessions_discarded_at",
        table_name="charging_sessions",
    )
    op.drop_column("charging_sessions", "discarded_at")
