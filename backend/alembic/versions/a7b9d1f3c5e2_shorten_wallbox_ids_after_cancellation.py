"""shorten wallbox ids of rebillable sessions

Die Migration f6a8c0e2b4d1 hat Ladevorgänge ausgelassen, die schon einmal in
einer inzwischen stornierten Rechnung standen. Diese sind wieder abrechenbar
und erhalten jetzt ebenfalls den Namen der Wallbox bzw. die Kurzform der ID.

Revision ID: a7b9d1f3c5e2
Revises: f6a8c0e2b4d1
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7b9d1f3c5e2"
down_revision: Union[str, Sequence[str], None] = "f6a8c0e2b4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nicht abgerechnet und nicht in einem Entwurf: Name der Wallbox (eigener
    # Name, sonst Name aus der Hager Cloud), sonst Kurzform "ID: ..XXXXX"
    op.execute(
        """
        UPDATE charging_sessions AS cs
        JOIN wallboxes AS wb ON wb.wallbox_id = cs.wallbox_id
        SET cs.station_id = COALESCE(
            wb.custom_name,
            wb.hager_name,
            CONCAT('ID: ..', RIGHT(cs.wallbox_id, 5))
        )
        WHERE cs.station_id LIKE 'ID: %'
          AND cs.station_id NOT LIKE 'ID: ..%'
          AND cs.invoiced = 0
          AND cs.id NOT IN (
              SELECT items.charging_session_id
              FROM invoice_items AS items
              JOIN invoices ON invoices.id = items.invoice_id
              WHERE invoices.status = 'draft'
                AND items.charging_session_id IS NOT NULL
          )
        """
    )


def downgrade() -> None:
    # Namen werden nicht zurückgesetzt
    pass
