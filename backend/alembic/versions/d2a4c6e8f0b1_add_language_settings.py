"""add language settings

Revision ID: d2a4c6e8f0b1
Revises: c8f1a3d5e7b9
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2a4c6e8f0b1"
down_revision: Union[str, Sequence[str], None] = "c8f1a3d5e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column("default_language", sa.String(length=5), nullable=False, server_default="de"),
    )
    # leer = Standardsprache des Mandanten
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "language")
    op.drop_column("global_settings", "default_language")
