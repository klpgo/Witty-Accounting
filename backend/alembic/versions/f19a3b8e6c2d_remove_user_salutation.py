"""remove user salutation field

Revision ID: f19a3b8e6c2d
Revises: e5f7a1c9d3b4
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f19a3b8e6c2d"
down_revision: Union[str, Sequence[str], None] = "e5f7a1c9d3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column(
        "users",
        "salutation",
    )


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "salutation",
            sa.String(length=50),
            nullable=True,
        ),
    )
