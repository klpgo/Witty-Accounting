"""add application settings

Revision ID: 36095c9651c1
Revises: 001ddd394c7d
Create Date: 2026-07-29 18:43:35.260193
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "36095c9651c1"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "001ddd394c7d"
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
            "app_name",
            sa.String(length=255),
            nullable=False,
            server_default="Witty-Accounting",
        ),
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_payment_term_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "invoice_payment_term_days",
    )

    op.drop_column(
        "global_settings",
        "app_name",
    )
