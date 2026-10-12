from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import billing_email
from app.services.billing_email import SummaryEntry


class FakeDb:
    def __init__(self, **settings) -> None:
        defaults = {
            "invoice_issuer_email": None,
            "smtp_use_database_settings": True,
            "mail_from_address": "absender@example.com",
            "frontend_base_url": "https://witty.example.com/",
            "default_language": "de",
            "locale": "de-DE",
        }
        defaults.update(settings)
        self.settings = SimpleNamespace(**defaults)

    def get(self, model, key):
        return self.settings


def make_invoice(language: str = "de") -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        language=language,
        locale="de-DE",
        currency="EUR",
        total_gross=Decimal("12.34"),
        service_period_start=datetime(2026, 10, 1),
        service_period_end=datetime(2026, 11, 1),
        review_due_date=date(2026, 11, 10),
        recipient_name="Kunde A",
    )


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []
    monkeypatch.setattr(
        billing_email,
        "send_plain_email",
        lambda db, **kwargs: sent.append(kwargs),
    )
    monkeypatch.setattr(billing_email, "_sender_name", lambda db: "Witty Test")
    return sent


def test_notification_address_is_the_issuer_email() -> None:
    # keine Ersatzadresse: ohne Angabe gibt es keinen Empfänger
    assert billing_email.notification_address(FakeDb()) is None
    assert (
        billing_email.notification_address(
            FakeDb(invoice_issuer_email=" rechnung@example.com ")
        )
        == "rechnung@example.com"
    )


def test_review_email_text() -> None:
    subject, body = billing_email.build_review_email(
        FakeDb(),
        invoice=make_invoice(),
        sender_name="Witty Test",
    )

    assert subject == (
        "Rechnungsentwurf zur Prüfung – Leistungszeitraum "
        "01.10.2026 – 31.10.2026"
    )
    assert "über 12,34 EUR" in body
    assert "https://witty.example.com/invoices/42" in body
    assert "am 10.11.2026 verbindlich erstellt" in body
    assert "„Nachfrage zum Rechnungsentwurf“" in body
    assert body.endswith("Witty Test\n")


def test_review_email_in_english() -> None:
    subject, body = billing_email.build_review_email(
        FakeDb(),
        invoice=make_invoice("en"),
        sender_name="Witty Test",
    )

    assert subject.startswith("Invoice draft for review")
    assert "“Question about the invoice draft”" in body


def test_inquiry_email_goes_to_issuer(outbox: list[dict]) -> None:
    user = SimpleNamespace(
        first_name="Kunde",
        last_name="A",
        email="kunde@example.com",
    )

    billing_email.send_inquiry_email(
        FakeDb(invoice_issuer_email="rechnung@example.com"),
        invoice=make_invoice(),
        user=user,
        contact_email="rechnung@example.com",
    )

    [mail] = outbox
    assert mail["recipient_email"] == "rechnung@example.com"
    assert mail["subject"] == "Rechnungsentwurf zurückgestellt – Kunde A"
    assert "Kunde A (kunde@example.com)" in mail["body"]
    assert "#42" in mail["body"]
    assert "https://witty.example.com/invoices/42" in mail["body"]


def test_finalized_summary_lists_sections(outbox: list[dict]) -> None:
    billing_email.send_finalized_email(
        FakeDb(invoice_issuer_email="rechnung@example.com"),
        sent=[SummaryEntry("RE-2026-000001 Kunde A")],
        postal=[SummaryEntry("RE-2026-000002 Kunde B")],
        failed=[SummaryEntry("#3 Kunde C", "SMTP down")],
        finalized_count=2,
    )

    [mail] = outbox
    assert mail["subject"] == (
        "Automatische Abrechnung: 2 Rechnung(en) finalisiert"
    )
    assert "Bitte per Post versenden:\n- RE-2026-000002 Kunde B" in mail["body"]
    assert "- #3 Kunde C: SMTP down" in mail["body"]
