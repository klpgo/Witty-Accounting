from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.models.invoice import Invoice, InvoiceItem
from app.services.invoice_pdf import (
    InvoiceNotFinalizedError,
    build_invoice_pdf,
)


def create_finalized_invoice() -> Invoice:
    invoice = Invoice(
        id=1,
        invoice_number="RE-2026-000001",
        user_id=1,
        issuer_name="Witty Accounting GmbH",
        issuer_address=(
            "Teststraße 1\n12345 Teststadt"
        ),
        issuer_tax_number="123/456/78901",
        issuer_vat_id=None,
        recipient_name="Max Mustermann",
        recipient_address=(
            "Musterweg 5\n54321 Musterstadt"
        ),
        status="finalized",
        issue_date=date(2026, 7, 5),
        due_date=date(2026, 7, 19),
        service_period_start=datetime(
            2026,
            6,
            1,
        ),
        service_period_end=datetime(
            2026,
            7,
            1,
        ),
        currency="EUR",
        total_net=Decimal("2.20"),
        vat_amount=Decimal("0.42"),
        total_gross=Decimal("2.62"),
        finalized_at=datetime(
            2026,
            7,
            5,
            10,
            0,
        ),
        pdf_storage_path=None,
        pdf_sha256=None,
        pdf_size_bytes=None,
        pdf_created_at=None,
    )

    invoice.items = [
        InvoiceItem(
            id=1,
            invoice_id=1,
            charging_session_id=1,
            position_number=1,
            description="Ladevorgang",
            session_start=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            session_end=datetime(
                2026,
                6,
                17,
                11,
                0,
            ),
            station_id="WB2",
            energy_total_kwh=Decimal(
                "10.0000"
            ),
            energy_grid_kwh=Decimal(
                "6.0000"
            ),
            energy_pv_kwh=Decimal(
                "4.0000"
            ),
            grid_price_net=Decimal(
                "0.3000"
            ),
            pv_price_net=Decimal(
                "0.1000"
            ),
            cost_grid_net=Decimal(
                "1.8000"
            ),
            cost_pv_net=Decimal(
                "0.4000"
            ),
            net_amount=Decimal("2.2000"),
            vat_rate=Decimal("19.00"),
            vat_amount=Decimal("0.42"),
            gross_amount=Decimal("2.62"),
        )
    ]

    return invoice


def test_builds_readable_invoice_pdf() -> None:
    invoice = create_finalized_invoice()

    pdf_bytes = build_invoice_pdf(invoice)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    assert len(reader.pages) == 1

    extracted_text = (
        reader.pages[0].extract_text()
        or ""
    )

    assert "RE-2026-000001" in extracted_text
    assert "Max Mustermann" in extracted_text
    assert "Rechnungsbetrag" in extracted_text
    assert "Gesamt" in extracted_text
    assert "Netz" in extracted_text
    assert "PV" in extracted_text
    assert "kWh" in extracted_text

    assert "10,0" in extracted_text
    assert "6,0" in extracted_text
    assert "4,0" in extracted_text

    assert (
        "innerhalb von 14 Tagen"
        in extracted_text
    )
    assert (
        "Zahlbar bis 19.07.2026"
        in extracted_text
    )


def test_rejects_draft_invoice() -> None:
    invoice = create_finalized_invoice()
    invoice.status = "draft"

    with pytest.raises(
        InvoiceNotFinalizedError
    ):
        build_invoice_pdf(invoice)
