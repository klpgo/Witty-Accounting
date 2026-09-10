"""add optional invoice Girocode setting

Revision ID: d71c9a4e6b20
Revises: 9c8a7b6d5e4f
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d71c9a4e6b20"
down_revision: Union[str, Sequence[str], None] = "9c8a7b6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_girocode_enabled",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "invoice_girocode_enabled",
    )
