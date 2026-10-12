"""prorated base fee slices

- monthly_base_fee_charges.slice_start / slice_end: abgerechneter Teil des
  Monats (anteilige Grundgebühr, z. B. bei wöchentlicher Abrechnung)
- bestehende Einträge erhalten den ganzen Monat
- Eindeutigkeit je Zuordnung, Monat und Teil statt je Zuordnung und Monat

Revision ID: e1f3a5b7c9d2
Revises: d0e2f4a6b8c1
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f3a5b7c9d2"
down_revision: Union[str, Sequence[str], None] = "d0e2f4a6b8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monthly_base_fee_charges",
        sa.Column("slice_start", sa.Date(), nullable=True),
    )
    op.add_column(
        "monthly_base_fee_charges",
        sa.Column("slice_end", sa.Date(), nullable=True),
    )
    op.execute(
        "UPDATE monthly_base_fee_charges "
        "SET slice_start = fee_month, "
        "slice_end = DATE_ADD(fee_month, INTERVAL 1 MONTH)"
    )
    # Neuer Index zuerst: der alte dient dem Fremdschlüssel auf
    # rfid_assignment_id und darf erst danach entfernt werden
    op.create_unique_constraint(
        "uq_monthly_base_fee_charges_assignment_slice",
        "monthly_base_fee_charges",
        ["rfid_assignment_id", "fee_month", "slice_start", "slice_end"],
    )
    op.drop_constraint(
        "uq_monthly_base_fee_charges_assignment_month",
        "monthly_base_fee_charges",
        type_="unique",
    )


def downgrade() -> None:
    # Schlägt fehl, wenn bereits anteilige Einträge (mehrere je Monat)
    # vorhanden sind – diese müssen vorher zusammengeführt werden
    op.create_unique_constraint(
        "uq_monthly_base_fee_charges_assignment_month",
        "monthly_base_fee_charges",
        ["rfid_assignment_id", "fee_month"],
    )
    op.drop_constraint(
        "uq_monthly_base_fee_charges_assignment_slice",
        "monthly_base_fee_charges",
        type_="unique",
    )
    op.drop_column("monthly_base_fee_charges", "slice_end")
    op.drop_column("monthly_base_fee_charges", "slice_start")
