"""add rfid card assignments

Revision ID: ffc7e2820fd9
Revises: 6233fc33622c
Create Date: 2026-07-28

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ffc7e2820fd9"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "6233fc33622c"
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
    """Add historical RFID-card assignments."""
    op.create_table(
        "rfid_card_assignments",
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
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "valid_to",
            sa.DateTime(),
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
            ["rfid_card_id"],
            ["rfid_cards.id"],
            name=(
                "fk_rfid_card_assignments_"
                "rfid_card_id_rfid_cards"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=(
                "fk_rfid_card_assignments_"
                "user_id_users"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=(
                "pk_rfid_card_assignments"
            ),
        ),
        sa.UniqueConstraint(
            "rfid_card_id",
            "valid_from",
            name=(
                "uq_rfid_card_assignments_"
                "card_valid_from"
            ),
        ),
    )

    op.create_index(
        "ix_rfid_card_assignments_user_id",
        "rfid_card_assignments",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_rfid_card_assignments_card_period",
        "rfid_card_assignments",
        [
            "rfid_card_id",
            "valid_from",
            "valid_to",
        ],
        unique=False,
    )

    op.add_column(
        "charging_sessions",
        sa.Column(
            "rfid_assignment_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_charging_sessions_rfid_assignment_id",
        "charging_sessions",
        ["rfid_assignment_id"],
        unique=False,
    )

    op.create_foreign_key(
        (
            "fk_charging_sessions_"
            "rfid_assignment_id_"
            "rfid_card_assignments"
        ),
        "charging_sessions",
        "rfid_card_assignments",
        ["rfid_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Jede bestehende Karte erhält zunächst eine
    # historische Zuordnung zu ihrem bisherigen Benutzer.
    op.execute(
        sa.text(
            """
            INSERT INTO rfid_card_assignments (
                rfid_card_id,
                user_id,
                valid_from,
                valid_to,
                created_at,
                updated_at
            )
            SELECT
                card.id,
                card.user_id,
                '1970-01-01 00:00:00',
                NULL,
                COALESCE(
                    card.created_at,
                    CURRENT_TIMESTAMP
                ),
                COALESCE(
                    card.updated_at,
                    CURRENT_TIMESTAMP
                )
            FROM rfid_cards AS card
            WHERE NOT EXISTS (
                SELECT 1
                FROM rfid_card_assignments
                    AS assignment
                WHERE
                    assignment.rfid_card_id
                    = card.id
                    AND assignment.valid_from
                    = '1970-01-01 00:00:00'
            )
            """
        )
    )

    # Bereits importierte Ladevorgänge werden mit
    # der historischen Zuordnung ihrer Karte verbunden.
    op.execute(
        sa.text(
            """
            UPDATE charging_sessions AS session
            INNER JOIN rfid_card_assignments
                AS assignment
                ON assignment.rfid_card_id
                    = session.rfid_card_id
                AND assignment.valid_from
                    = '1970-01-01 00:00:00'
            SET session.rfid_assignment_id
                = assignment.id
            WHERE
                session.rfid_card_id IS NOT NULL
                AND session.rfid_assignment_id
                    IS NULL
            """
        )
    )


def downgrade() -> None:
    """Remove historical RFID-card assignments."""
    op.drop_constraint(
        (
            "fk_charging_sessions_"
            "rfid_assignment_id_"
            "rfid_card_assignments"
        ),
        "charging_sessions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_charging_sessions_rfid_assignment_id",
        table_name="charging_sessions",
    )

    op.drop_column(
        "charging_sessions",
        "rfid_assignment_id",
    )

    op.drop_index(
        "ix_rfid_card_assignments_card_period",
        table_name="rfid_card_assignments",
    )

    op.drop_index(
        "ix_rfid_card_assignments_user_id",
        table_name="rfid_card_assignments",
    )

    op.drop_table(
        "rfid_card_assignments"
    )
