"""add rfid number to charging sessions

Revision ID: 9d4c1e7a2b58
Revises: 7b3e9d2f4a61
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d4c1e7a2b58"
down_revision: Union[str, Sequence[str], None] = "7b3e9d2f4a61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "charging_sessions",
        sa.Column(
            "rfid_number",
            sa.String(length=32),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_charging_sessions_rfid_number",
        "charging_sessions",
        ["rfid_number"],
    )

    # Bereits zugeordnete Ladevorgänge: Nummer aus der Karte übernehmen
    op.execute(
        """
        UPDATE charging_sessions
        SET rfid_number = (
            SELECT rfid_cards.rfid_number
            FROM rfid_cards
            WHERE rfid_cards.id = charging_sessions.rfid_card_id
        )
        WHERE rfid_card_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_charging_sessions_rfid_number",
        table_name="charging_sessions",
    )

    op.drop_column(
        "charging_sessions",
        "rfid_number",
    )
