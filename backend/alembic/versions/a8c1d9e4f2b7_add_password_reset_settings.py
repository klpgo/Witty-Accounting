"""add password reset settings

Revision ID: a8c1d9e4f2b7
Revises: 74f0f84b195d
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings


revision: str = "a8c1d9e4f2b7"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "74f0f84b195d"
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
    frontend_base_url = (
        settings.frontend_base_url.strip().rstrip("/")
        or "http://localhost:5173"
    )
    expire_minutes = max(
        1,
        min(
            settings.password_reset_token_expire_minutes,
            10080,
        ),
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "frontend_base_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "password_reset_token_expire_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )

    global_settings = sa.table(
        "global_settings",
        sa.column(
            "frontend_base_url",
            sa.String(length=2048),
        ),
        sa.column(
            "password_reset_token_expire_minutes",
            sa.Integer(),
        ),
    )
    op.execute(
        global_settings.update().values(
            frontend_base_url=frontend_base_url,
            password_reset_token_expire_minutes=(
                expire_minutes
            ),
        )
    )

    op.alter_column(
        "global_settings",
        "frontend_base_url",
        existing_type=sa.String(length=2048),
        nullable=False,
        server_default="http://localhost:5173",
    )
    op.alter_column(
        "global_settings",
        "password_reset_token_expire_minutes",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="60",
    )


def downgrade() -> None:
    op.drop_column(
        "global_settings",
        "password_reset_token_expire_minutes",
    )
    op.drop_column(
        "global_settings",
        "frontend_base_url",
    )
