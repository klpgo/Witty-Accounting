"""remove legacy rfid card user

Revision ID: faecd941c530
Revises: ffc7e2820fd9

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "faecd941c530"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "ffc7e2820fd9"
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
    """Remove the obsolete direct user assignment."""
    op.drop_constraint(
        "rfid_cards_ibfk_1",
        "rfid_cards",
        type_="foreignkey",
    )

    op.drop_index(
        "user_id",
        table_name="rfid_cards",
    )

    op.drop_column(
        "rfid_cards",
        "user_id",
    )


def downgrade() -> None:
    """Restore the former direct user assignment."""
    op.add_column(
        "rfid_cards",
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Für jede Karte wird beim Downgrade die aktuell
    # offene beziehungsweise zuletzt gültige Zuordnung
    # als Legacy-Benutzer übernommen.
    op.execute(
        sa.text(
            """
            UPDATE rfid_cards AS card
            SET card.user_id = (
                SELECT assignment.user_id
                FROM rfid_card_assignments
                    AS assignment
                WHERE assignment.rfid_card_id
                    = card.id
                ORDER BY
                    (
                        assignment.valid_to
                        IS NULL
                    ) DESC,
                    assignment.valid_from DESC,
                    assignment.id DESC
                LIMIT 1
            )
            """
        )
    )

    bind = op.get_bind()

    missing_user_count = bind.scalar(
        sa.text(
            """
            SELECT COUNT(*)
            FROM rfid_cards
            WHERE user_id IS NULL
            """
        )
    )

    if missing_user_count:
        raise RuntimeError(
            "Das Downgrade kann nicht fortgesetzt "
            "werden: Mindestens eine RFID-Karte "
            "besitzt keine Benutzerzuordnung."
        )

    op.alter_column(
        "rfid_cards",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_index(
        "user_id",
        "rfid_cards",
        ["user_id"],
        unique=False,
    )

    op.create_foreign_key(
        "rfid_cards_ibfk_1",
        "rfid_cards",
        "users",
        ["user_id"],
        ["id"],
    )
