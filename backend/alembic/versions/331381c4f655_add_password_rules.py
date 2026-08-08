"""add password rules

Revision ID: 331381c4f655
Revises: 736482e7757d
Create Date: 2026-07-31 16:32:30.765993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '331381c4f655'
down_revision: Union[str, Sequence[str], None] = '736482e7757d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "password_min_length",
            sa.Integer(),
            nullable=False,
            server_default="8",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "password_require_uppercase",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "password_require_lowercase",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "password_require_digit",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "password_require_special",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "password_require_special",
    )
    op.drop_column(
        "global_settings",
        "password_require_digit",
    )
    op.drop_column(
        "global_settings",
        "password_require_lowercase",
    )
    op.drop_column(
        "global_settings",
        "password_require_uppercase",
    )
    op.drop_column(
        "global_settings",
        "password_min_length",
    )
