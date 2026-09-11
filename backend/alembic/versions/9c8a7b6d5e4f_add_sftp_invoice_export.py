"""add SFTP invoice export

Revision ID: 9c8a7b6d5e4f
Revises: 4f6a2b8c1d3e
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c8a7b6d5e4f"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "4f6a2b8c1d3e"
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
            "invoice_export_sftp_enabled",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_export_sftp_host",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_export_sftp_port",
            sa.Integer(),
            server_default="22",
            nullable=False,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_export_sftp_username",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_export_sftp_directory",
            sa.String(length=1024),
            nullable=True,
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "pdf_exported_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "pdf_exported_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "pdf_export_remote_path",
            sa.String(length=1200),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "invoices",
        "pdf_export_remote_path",
    )
    op.drop_column(
        "invoices",
        "pdf_exported_by_user_id",
    )
    op.drop_column(
        "invoices",
        "pdf_exported_at",
    )
    op.drop_column(
        "global_settings",
        "invoice_export_sftp_directory",
    )
    op.drop_column(
        "global_settings",
        "invoice_export_sftp_username",
    )
    op.drop_column(
        "global_settings",
        "invoice_export_sftp_port",
    )
    op.drop_column(
        "global_settings",
        "invoice_export_sftp_host",
    )
    op.drop_column(
        "global_settings",
        "invoice_export_sftp_enabled",
    )
