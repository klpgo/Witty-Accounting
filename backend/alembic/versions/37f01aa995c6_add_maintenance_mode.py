"""add maintenance mode

Revision ID: 37f01aa995c6
Revises: 331381c4f655
Create Date: 2026-07-31 22:38:17.850751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37f01aa995c6'
down_revision: Union[str, Sequence[str], None] = '331381c4f655'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "maintenance_mode",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "maintenance_mode",
    )
