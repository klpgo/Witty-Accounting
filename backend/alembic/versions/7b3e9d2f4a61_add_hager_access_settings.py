"""add hager access settings

Revision ID: 7b3e9d2f4a61
Revises: f19a3b8e6c2d
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b3e9d2f4a61"
down_revision: Union[str, Sequence[str], None] = "f19a3b8e6c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "hager_username",
            sa.String(length=320),
            nullable=True,
        ),
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "hager_password_encrypted",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "hager_installation_id",
            sa.String(length=50),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "hager_installation_id",
    )

    op.drop_column(
        "global_settings",
        "hager_password_encrypted",
    )

    op.drop_column(
        "global_settings",
        "hager_username",
    )
