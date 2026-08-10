"""split base fee by RFID assignment

Revision ID: 4f6a2b8c1d3e
Revises: d91e6f4a2b73
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op


revision: str = "4f6a2b8c1d3e"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "d91e6f4a2b73"
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
    op.drop_constraint(
        "uq_monthly_base_fee_charges_card_month",
        "monthly_base_fee_charges",
        type_="unique",
    )
    op.create_unique_constraint(
        (
            "uq_monthly_base_fee_charges_"
            "assignment_month"
        ),
        "monthly_base_fee_charges",
        [
            "rfid_assignment_id",
            "fee_month",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        (
            "uq_monthly_base_fee_charges_"
            "assignment_month"
        ),
        "monthly_base_fee_charges",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_monthly_base_fee_charges_card_month",
        "monthly_base_fee_charges",
        [
            "rfid_card_id",
            "fee_month",
        ],
    )
