"""add smtp settings

Revision ID: 736482e7757d
Revises: b2689e6b406e
Create Date: 2026-07-31 12:58:23.432926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '736482e7757d'
down_revision: Union[str, Sequence[str], None] = 'b2689e6b406e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_use_database_settings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_sending_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_host",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_port",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_timeout_seconds",
            sa.Numeric(precision=8, scale=2),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_starttls",
            sa.Boolean(),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_username",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "smtp_password_encrypted",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_from_address",
            sa.String(length=320),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_from_name",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "mail_from_name",
    )
    op.drop_column(
        "global_settings",
        "mail_from_address",
    )
    op.drop_column(
        "global_settings",
        "smtp_password_encrypted",
    )
    op.drop_column(
        "global_settings",
        "smtp_username",
    )
    op.drop_column(
        "global_settings",
        "smtp_starttls",
    )
    op.drop_column(
        "global_settings",
        "smtp_timeout_seconds",
    )
    op.drop_column(
        "global_settings",
        "smtp_port",
    )
    op.drop_column(
        "global_settings",
        "smtp_host",
    )
    op.drop_column(
        "global_settings",
        "mail_sending_enabled",
    )
    op.drop_column(
        "global_settings",
        "smtp_use_database_settings",
    )
