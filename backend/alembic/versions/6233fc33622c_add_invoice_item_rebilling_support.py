"""add invoice item rebilling support

Revision ID: 6233fc33622c
Revises: 24fe85ab2bd0
Create Date: 2026-07-25 23:42:35.444427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6233fc33622c'
down_revision: Union[str, Sequence[str], None] = '24fe85ab2bd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Add support for invoice-item rebilling."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    column_names = {
        column["name"]
        for column in inspector.get_columns(
            "invoice_items"
        )
    }

    # MariaDB uses non-transactional DDL. The column
    # may already exist after an interrupted migration.
    if "rebills_invoice_item_id" not in column_names:
        op.add_column(
            "invoice_items",
            sa.Column(
                "rebills_invoice_item_id",
                sa.Integer(),
                nullable=True,
            ),
        )

    index_names = {
        index["name"]
        for index in sa.inspect(
            bind
        ).get_indexes("invoice_items")
    }

    # The foreign key on charging_session_id needs a
    # supporting index before its unique index is removed.
    if (
        "ix_invoice_items_charging_session_id"
        not in index_names
    ):
        op.create_index(
            "ix_invoice_items_charging_session_id",
            "invoice_items",
            ["charging_session_id"],
            unique=False,
        )

    index_names = {
        index["name"]
        for index in sa.inspect(
            bind
        ).get_indexes("invoice_items")
    }

    if "charging_session_id" in index_names:
        op.drop_index(
            "charging_session_id",
            table_name="invoice_items",
        )

    unique_name = (
        "uq_invoice_items_rebills_invoice_item_id"
    )

    unique_names = {
        constraint["name"]
        for constraint in sa.inspect(
            bind
        ).get_unique_constraints(
            "invoice_items"
        )
        if constraint["name"] is not None
    }

    index_names = {
        index["name"]
        for index in sa.inspect(
            bind
        ).get_indexes("invoice_items")
    }

    if (
        unique_name not in unique_names
        and unique_name not in index_names
    ):
        op.create_unique_constraint(
            unique_name,
            "invoice_items",
            ["rebills_invoice_item_id"],
        )

    foreign_key_name = (
        "fk_invoice_items_rebills_invoice_item_id_"
        "invoice_items"
    )

    foreign_key_names = {
        foreign_key["name"]
        for foreign_key in sa.inspect(
            bind
        ).get_foreign_keys("invoice_items")
        if foreign_key["name"] is not None
    }

    if foreign_key_name not in foreign_key_names:
        op.create_foreign_key(
            foreign_key_name,
            "invoice_items",
            "invoice_items",
            ["rebills_invoice_item_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Remove support for invoice-item rebilling."""
    op.drop_constraint(
        (
            "fk_invoice_items_rebills_invoice_item_id_"
            "invoice_items"
        ),
        "invoice_items",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_invoice_items_rebills_invoice_item_id",
        "invoice_items",
        type_="unique",
    )

    op.drop_column(
        "invoice_items",
        "rebills_invoice_item_id",
    )

    # Restore the original unique index before removing
    # the replacement index required by the foreign key.
    op.create_index(
        "charging_session_id",
        "invoice_items",
        ["charging_session_id"],
        unique=True,
    )

    op.drop_index(
        "ix_invoice_items_charging_session_id",
        table_name="invoice_items",
    )
