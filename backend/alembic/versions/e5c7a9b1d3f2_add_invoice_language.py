"""add invoice language

Revision ID: e5c7a9b1d3f2
Revises: d2a4c6e8f0b1
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5c7a9b1d3f2"
down_revision: Union[str, Sequence[str], None] = "d2a4c6e8f0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bestehende Rechnungen bleiben ohne Angabe und erscheinen wie bisher
    # auf Deutsch; neue Rechnungen halten ihre Sprache fest.
    op.add_column(
        "invoices",
        sa.Column("language", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "language")
