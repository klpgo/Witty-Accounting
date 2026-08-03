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
from app.services.invoice_pdfa import (
    InvoicePdfAError,
    convert_to_pdfa_2b,
    validate_pdfa_2b_structure,
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
        issuer_bank_name="Musterbank",
        issuer_iban="DE89370400440532013000",
        issuer_bic="COBADEFFXXX",
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
            item_type="charging_session",
            monthly_base_fee_charge_id=None,
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
    assert "Bankverbindung" in extracted_text
    assert "Musterbank" in extracted_text
    assert (
        "DE89370400440532013000"
        in extracted_text
    )
    assert "COBADEFFXXX" in extracted_text


def test_builds_monthly_base_fee_invoice_pdf() -> None:
    invoice = create_finalized_invoice()

    invoice.service_period_start = datetime(
        2026,
        7,
        1,
    )
    invoice.service_period_end = datetime(
        2026,
        8,
        1,
    )
    invoice.total_net = Decimal("10.00")
    invoice.vat_amount = Decimal("1.90")
    invoice.total_gross = Decimal("11.90")

    invoice.items = [
        InvoiceItem(
            id=2,
            invoice_id=invoice.id,
            item_type="monthly_base_fee",
            monthly_base_fee_charge_id=1,
            charging_session_id=None,
            reversed_invoice_item_id=None,
            rebills_invoice_item_id=None,
            position_number=1,
            description=(
                "Monatliche Grundgebühr RFID-Karte "
                "BASE-FEE-CARD – Juli 2026"
            ),
            session_start=None,
            session_end=None,
            station_id=None,
            energy_total_kwh=None,
            energy_grid_kwh=None,
            energy_pv_kwh=None,
            grid_price_net=None,
            pv_price_net=None,
            cost_grid_net=None,
            cost_pv_net=None,
            net_amount=Decimal("10.0000"),
            vat_rate=Decimal("19.00"),
            vat_amount=Decimal("1.90"),
            gross_amount=Decimal("11.90"),
        )
    ]

    pdf_bytes = build_invoice_pdf(invoice)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    extracted_text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    assert "Monatliche Grundgebühr" in extracted_text
    assert "BASE-FEE-CARD" in extracted_text
    assert "Juli 2026" in extracted_text
    assert "10,00" in extracted_text
    assert "19,00" in extracted_text
    assert "11,90" in extracted_text


def test_converts_invoice_to_pdfa_2b() -> None:
    invoice = create_finalized_invoice()

    pdf_bytes = convert_to_pdfa_2b(
        build_invoice_pdf(invoice)
    )

    validate_pdfa_2b_structure(pdf_bytes)

    reader = PdfReader(BytesIO(pdf_bytes))
    root = reader.trailer["/Root"]

    assert root.get("/OutputIntents")

    metadata = (
        root["/Metadata"]
        .get_object()
        .get_data()
    )

    assert b"pdfaid:part='2'" in metadata
    assert b"pdfaid:conformance='B'" in metadata

    extracted_text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    assert "RE-2026-000001" in extracted_text
    assert "Max Mustermann" in extracted_text


def test_rejects_standard_pdf_as_pdfa_2b() -> None:
    invoice = create_finalized_invoice()

    with pytest.raises(InvoicePdfAError):
        validate_pdfa_2b_structure(
            build_invoice_pdf(invoice)
        )


def test_rejects_draft_invoice() -> None:
    invoice = create_finalized_invoice()
    invoice.status = "draft"

    with pytest.raises(
        InvoiceNotFinalizedError
    ):
        build_invoice_pdf(invoice)
