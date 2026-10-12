"""add wallboxes

Revision ID: f6a8c0e2b4d1
Revises: e5c7a9b1d3f2
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a8c0e2b4d1"
down_revision: Union[str, Sequence[str], None] = "e5c7a9b1d3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wallboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wallbox_id", sa.String(length=64), nullable=False),
        sa.Column("hager_name", sa.String(length=100), nullable=True),
        sa.Column("custom_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wallbox_id"),
    )

    # Bekannte Wallboxen aus den Ladevorgängen übernehmen; Name aus der
    # Hager Cloud ist der zuletzt gespeicherte Stationsname, sofern es keine
    # Notlösung "ID: …" war
    op.execute(
        """
        INSERT INTO wallboxes (wallbox_id, hager_name, created_at, updated_at)
        SELECT
            cs.wallbox_id,
            (
                SELECT named.station_id
                FROM charging_sessions AS named
                WHERE named.wallbox_id = cs.wallbox_id
                  AND named.station_id NOT LIKE 'ID: %'
                ORDER BY named.start_time DESC
                LIMIT 1
            ),
            UTC_TIMESTAMP(),
            UTC_TIMESTAMP()
        FROM charging_sessions AS cs
        WHERE cs.wallbox_id IS NOT NULL
        GROUP BY cs.wallbox_id
        """
    )

    # Nicht abgerechnete Ladevorgänge ohne Namen: lange ID durch die
    # Kurzform "ID: ..XXXXX" ersetzen
    op.execute(
        """
        UPDATE charging_sessions
        SET station_id = CONCAT('ID: ..', RIGHT(wallbox_id, 5))
        WHERE wallbox_id IS NOT NULL
          AND station_id LIKE 'ID: %'
          AND station_id NOT LIKE 'ID: ..%'
          AND invoiced = 0
          AND id NOT IN (
              SELECT items.charging_session_id
              FROM invoice_items AS items
              JOIN invoices ON invoices.id = items.invoice_id
              WHERE invoices.status = 'draft'
                AND items.charging_session_id IS NOT NULL
          )
        """
    )


def downgrade() -> None:
    op.drop_table("wallboxes")
