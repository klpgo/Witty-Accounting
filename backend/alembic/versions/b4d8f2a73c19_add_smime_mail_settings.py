"""add S/MIME mail settings

Revision ID: b4d8f2a73c19
Revises: 8b7d4c2a1e90
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings


revision: str = "b4d8f2a73c19"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "8b7d4c2a1e90"
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
    enabled_default = (
        "1" if settings.mail_smime_enabled else "0"
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "mail_smime_enabled",
            sa.Boolean(),
            server_default=enabled_default,
            nullable=False,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_smime_pkcs12_data",
            sa.LargeBinary(length=65535),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_smime_pkcs12_filename",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "mail_smime_pkcs12_password_encrypted",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "mail_smime_pkcs12_password_encrypted",
    )
    op.drop_column(
        "global_settings",
        "mail_smime_pkcs12_filename",
    )
    op.drop_column(
        "global_settings",
        "mail_smime_pkcs12_data",
    )
    op.drop_column(
        "global_settings",
        "mail_smime_enabled",
    )
