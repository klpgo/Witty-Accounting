"""add monthly base fees

Revision ID: 001ddd394c7d
Revises: faecd941c530
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001ddd394c7d"
down_revision: str | None = "faecd941c530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "global_settings",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "monthly_base_fee_net",
            sa.Numeric(
                precision=12,
                scale=4,
            ),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "monthly_base_fee_vat_rate",
            sa.Numeric(
                precision=5,
                scale=2,
            ),
            server_default=sa.text("19.00"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_global_settings",
        ),
    )

    op.execute(
        """
        INSERT INTO global_settings (
            id,
            monthly_base_fee_net,
            monthly_base_fee_vat_rate,
            created_at,
            updated_at
        )
        VALUES (
            1,
            0.0000,
            19.00,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """
    )

    op.create_table(
        "monthly_base_fee_charges",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "rfid_card_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "rfid_assignment_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "fee_month",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "net_amount",
            sa.Numeric(
                precision=12,
                scale=4,
            ),
            nullable=False,
        ),
        sa.Column(
            "vat_rate",
            sa.Numeric(
                precision=5,
                scale=2,
            ),
            nullable=False,
        ),
        sa.Column(
            "invoiced",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=(
                "fk_monthly_base_fee_charges_"
                "invoice"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rfid_assignment_id"],
            ["rfid_card_assignments.id"],
            name=(
                "fk_monthly_base_fee_charges_"
                "rfid_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rfid_card_id"],
            ["rfid_cards.id"],
            name=(
                "fk_monthly_base_fee_charges_"
                "rfid_card"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=(
                "fk_monthly_base_fee_charges_"
                "user"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_monthly_base_fee_charges",
        ),
        sa.UniqueConstraint(
            "rfid_card_id",
            "fee_month",
            name=(
                "uq_monthly_base_fee_charges_"
                "card_month"
            ),
        ),
    )

    op.create_index(
        "ix_monthly_base_fee_charges_user_month",
        "monthly_base_fee_charges",
        [
            "user_id",
            "fee_month",
        ],
        unique=False,
    )

    op.add_column(
        "invoice_items",
        sa.Column(
            "item_type",
            sa.String(length=30),
            server_default=sa.text(
                "'charging_session'"
            ),
            nullable=False,
        ),
    )

    op.add_column(
        "invoice_items",
        sa.Column(
            "monthly_base_fee_charge_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_invoice_items_monthly_base_fee_charge",
        "invoice_items",
        "monthly_base_fee_charges",
        ["monthly_base_fee_charge_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_invoice_items_monthly_base_fee_charge_id",
        "invoice_items",
        ["monthly_base_fee_charge_id"],
        unique=False,
    )

    op.alter_column(
        "invoice_items",
        "session_start",
        existing_type=sa.DateTime(),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "session_end",
        existing_type=sa.DateTime(),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "station_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "energy_total_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "energy_grid_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "energy_pv_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "grid_price_net",
        existing_type=sa.Numeric(
            precision=10,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "pv_price_net",
        existing_type=sa.Numeric(
            precision=10,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "cost_grid_net",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=True,
    )

    op.alter_column(
        "invoice_items",
        "cost_pv_net",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE invoice_items
        SET
            session_start = COALESCE(
                session_start,
                '1970-01-01 00:00:00'
            ),
            session_end = COALESCE(
                session_end,
                '1970-01-01 00:00:00'
            ),
            station_id = COALESCE(
                station_id,
                'MONTHLY_BASE_FEE'
            ),
            energy_total_kwh = COALESCE(
                energy_total_kwh,
                0.0000
            ),
            energy_grid_kwh = COALESCE(
                energy_grid_kwh,
                0.0000
            ),
            energy_pv_kwh = COALESCE(
                energy_pv_kwh,
                0.0000
            ),
            grid_price_net = COALESCE(
                grid_price_net,
                0.0000
            ),
            pv_price_net = COALESCE(
                pv_price_net,
                0.0000
            ),
            cost_grid_net = COALESCE(
                cost_grid_net,
                0.0000
            ),
            cost_pv_net = COALESCE(
                cost_pv_net,
                0.0000
            )
        """
    )

    op.alter_column(
        "invoice_items",
        "cost_pv_net",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "cost_grid_net",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "pv_price_net",
        existing_type=sa.Numeric(
            precision=10,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "grid_price_net",
        existing_type=sa.Numeric(
            precision=10,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "energy_pv_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "energy_grid_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "energy_total_kwh",
        existing_type=sa.Numeric(
            precision=12,
            scale=4,
        ),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "station_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "session_end",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    op.alter_column(
        "invoice_items",
        "session_start",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    op.drop_index(
        "ix_invoice_items_monthly_base_fee_charge_id",
        table_name="invoice_items",
    )

    op.drop_constraint(
        "fk_invoice_items_monthly_base_fee_charge",
        "invoice_items",
        type_="foreignkey",
    )

    op.drop_column(
        "invoice_items",
        "monthly_base_fee_charge_id",
    )

    op.drop_column(
        "invoice_items",
        "item_type",
    )

    op.drop_index(
        "ix_monthly_base_fee_charges_user_month",
        table_name="monthly_base_fee_charges",
    )

    op.drop_table("monthly_base_fee_charges")
    op.drop_table("global_settings")
