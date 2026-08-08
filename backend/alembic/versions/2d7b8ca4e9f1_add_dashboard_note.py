"""add dashboard note

Revision ID: 2d7b8ca4e9f1
Revises: fe3b4b16c708
Create Date: 2026-08-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d7b8ca4e9f1"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "fe3b4b16c708"
branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None
depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "dashboard_note",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "dashboard_note",
    )
