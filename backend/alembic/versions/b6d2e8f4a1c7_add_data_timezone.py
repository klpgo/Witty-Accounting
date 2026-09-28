"""add data timezone

Revision ID: b6d2e8f4a1c7
Revises: a9e3c7b5d2f1
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6d2e8f4a1c7"
down_revision: Union[str, Sequence[str], None] = "a9e3c7b5d2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bleibt leer und wird beim ersten Import mit der eingestellten
    # Zeitzone belegt (bisher war sie immer Europe/Berlin).
    op.add_column(
        "global_settings",
        sa.Column("data_timezone", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("global_settings", "data_timezone")
