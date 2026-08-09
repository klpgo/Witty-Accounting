"""create tenant registry

Revision ID: 6f3ce20d8f51
Revises:
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f3ce20d8f51"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = None
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
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "db_host",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "db_port",
            sa.Integer(),
            server_default="3306",
            nullable=False,
        ),
        sa.Column(
            "db_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "db_user",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "db_password_encrypted",
            sa.String(length=1000),
            nullable=False,
        ),
        sa.Column(
            "archive_namespace",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "config_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("archive_namespace"),
    )
    op.create_table(
        "tenant_domains",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "hostname",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "canonical",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hostname"),
    )
    op.create_index(
        "ix_tenant_domains_tenant_id",
        "tenant_domains",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_domains_tenant_id",
        table_name="tenant_domains",
    )
    op.drop_table("tenant_domains")
    op.drop_table("tenants")
