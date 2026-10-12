"""add automatic billing

- neue Tabelle billing_runs (Abrechnungsläufe)
- invoices: billing_run_id, review_status, review_due_date,
  review_notified_at, inquiry_at, delivery_status,
  notification_attempts, notification_error
- global_settings: auto_billing_* (Zeitplan, Fristen, Hinweisadresse)

Revision ID: d0e2f4a6b8c1
Revises: c9d1e3f5a7b4
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e2f4a6b8c1"
down_revision: Union[str, Sequence[str], None] = "c9d1e3f5a7b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("interval", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="waiting_for_data",
        ),
        sa.Column("review_due_date", sa.Date(), nullable=True),
        sa.Column(
            "drafts_created",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("waiting_notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("drafts_created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "period_start",
            name="uq_billing_runs_period_start",
        ),
    )
    op.create_index(
        "ix_billing_runs_period_end",
        "billing_runs",
        ["period_end"],
    )

    op.add_column(
        "invoices",
        sa.Column("billing_run_id", sa.Integer(), nullable=True),
    )
    # Index vor dem Fremdschlüssel anlegen, sonst legt MariaDB einen
    # zusätzlichen eigenen Index an
    op.create_index(
        "ix_invoices_billing_run_id",
        "invoices",
        ["billing_run_id"],
    )
    op.create_foreign_key(
        "fk_invoices_billing_run_id",
        "invoices",
        "billing_runs",
        ["billing_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "invoices",
        sa.Column("review_status", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_invoices_review_status",
        "invoices",
        ["review_status"],
    )
    op.add_column(
        "invoices",
        sa.Column("review_due_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("review_notified_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("inquiry_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("delivery_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "notification_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoices",
        sa.Column("notification_error", sa.String(500), nullable=True),
    )

    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_interval",
            sa.String(20),
            nullable=False,
            server_default="monthly",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_cutoff_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_grace_days",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_review_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_run_time",
            sa.String(5),
            nullable=False,
            server_default="06:00",
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_notification_email",
            sa.String(320),
            nullable=True,
        ),
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "auto_billing_active_since",
            sa.Date(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    for column in (
        "auto_billing_active_since",
        "auto_billing_notification_email",
        "auto_billing_run_time",
        "auto_billing_review_days",
        "auto_billing_grace_days",
        "auto_billing_cutoff_day",
        "auto_billing_interval",
        "auto_billing_enabled",
    ):
        op.drop_column("global_settings", column)

    for column in (
        "notification_error",
        "notification_attempts",
        "delivery_status",
        "inquiry_at",
        "review_notified_at",
        "review_due_date",
    ):
        op.drop_column("invoices", column)

    op.drop_index("ix_invoices_review_status", table_name="invoices")
    op.drop_column("invoices", "review_status")
    op.drop_constraint(
        "fk_invoices_billing_run_id",
        "invoices",
        type_="foreignkey",
    )
    op.drop_index("ix_invoices_billing_run_id", table_name="invoices")
    op.drop_column("invoices", "billing_run_id")

    op.drop_index("ix_billing_runs_period_end", table_name="billing_runs")
    op.drop_table("billing_runs")
