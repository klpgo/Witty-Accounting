"""add invoice pdf format

Revision ID: 74f0f84b195d
Revises: 2d7b8ca4e9f1
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "74f0f84b195d"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "2d7b8ca4e9f1"
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
            "invoice_pdf_format",
            sa.String(length=20),
            server_default="standard",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "invoice_pdf_format",
    )
