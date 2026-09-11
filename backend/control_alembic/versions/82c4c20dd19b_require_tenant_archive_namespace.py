"""require tenant archive namespace

Revision ID: 82c4c20dd19b
Revises: 6f3ce20d8f51
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "82c4c20dd19b"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "6f3ce20d8f51"
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
    op.execute(
        sa.text(
            "UPDATE tenants "
            "SET archive_namespace = slug "
            "WHERE archive_namespace IS NULL"
        )
    )
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.alter_column(
            "archive_namespace",
            existing_type=sa.String(length=100),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.alter_column(
            "archive_namespace",
            existing_type=sa.String(length=100),
            nullable=True,
        )
