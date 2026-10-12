"""issuer email in the invoice issuer data

- global_settings.auto_billing_notification_email wird zu
  invoice_issuer_email (Daten des Rechnungsstellers)
- global_settings.invoice_issuer_email_on_invoice: Adresse auf der Rechnung
- invoices.issuer_email: Adresse zum Zeitpunkt der Rechnung

Bisher stand die Absenderadresse der E-Mails (mail_from_address aus der
Datenbank) immer auf der Rechnung. Damit Rechnungen nach dem Update gleich
aussehen, wird diese Adresse übernommen, wenn noch keine eigene eingetragen
war, und die Anzeige auf der Rechnung eingeschaltet, sobald eine Adresse
vorhanden ist. Offene Entwürfe erhalten die Adresse ebenfalls.

Revision ID: f2a4c6e8b0d3
Revises: e1f3a5b7c9d2
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a4c6e8b0d3"
down_revision: Union[str, Sequence[str], None] = "e1f3a5b7c9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "global_settings",
        "auto_billing_notification_email",
        new_column_name="invoice_issuer_email",
        existing_type=sa.String(320),
        existing_nullable=True,
    )
    op.add_column(
        "global_settings",
        sa.Column(
            "invoice_issuer_email_on_invoice",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "invoices",
        sa.Column("issuer_email", sa.String(320), nullable=True),
    )

    op.execute(
        "UPDATE global_settings "
        "SET invoice_issuer_email = NULLIF(TRIM(mail_from_address), '') "
        "WHERE (invoice_issuer_email IS NULL OR TRIM(invoice_issuer_email) = '') "
        "AND smtp_use_database_settings = 1"
    )
    op.execute(
        "UPDATE global_settings "
        "SET invoice_issuer_email_on_invoice = 1 "
        "WHERE invoice_issuer_email IS NOT NULL "
        "AND TRIM(invoice_issuer_email) <> ''"
    )
    op.execute(
        "UPDATE invoices SET issuer_email = ("
        "SELECT invoice_issuer_email FROM global_settings "
        "WHERE global_settings.id = 1 "
        "AND global_settings.invoice_issuer_email_on_invoice = 1"
        ") WHERE status = 'draft'"
    )


def downgrade() -> None:
    op.drop_column("invoices", "issuer_email")
    op.drop_column("global_settings", "invoice_issuer_email_on_invoice")
    op.alter_column(
        "global_settings",
        "invoice_issuer_email",
        new_column_name="auto_billing_notification_email",
        existing_type=sa.String(320),
        existing_nullable=True,
    )
