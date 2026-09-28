"""add locale and currency

Revision ID: c8f1a3d5e7b9
Revises: b6d2e8f4a1c7
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f1a3d5e7b9"
down_revision: Union[str, Sequence[str], None] = "b6d2e8f4a1c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column("locale", sa.String(length=10), nullable=False, server_default="de-DE"),
    )
    op.add_column(
        "global_settings",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
    )
    # Bestehende Rechnungen bleiben ohne Angabe und erscheinen wie bisher
    # in de-DE; neue Rechnungen halten das Gebietsschema fest.
    op.add_column(
        "invoices",
        sa.Column("locale", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "locale")
    op.drop_column("global_settings", "currency")
    op.drop_column("global_settings", "locale")
