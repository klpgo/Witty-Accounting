from datetime import date
from decimal import Decimal
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas as pdf_canvas

from app.models.invoice import Invoice


class InvoicePdfError(Exception):
    """Base exception for invoice PDF generation."""


class InvoiceNotFinalizedError(InvoicePdfError):
    """Raised when a draft invoice is rendered."""


class IncompleteInvoicePdfDataError(
    InvoicePdfError
):
    """Raised when required invoice data is missing."""

CONTENT_WIDTH = A4[0] - 36 * mm

def format_decimal(
    value: Decimal,
    decimal_places: int,
) -> str:
    quantizer = Decimal("1").scaleb(
        -decimal_places
    )
    formatted = f"{value.quantize(quantizer):,.{decimal_places}f}"

    return (
        formatted
        .replace(",", "#")
        .replace(".", ",")
        .replace("#", ".")
    )


def format_money(value: Decimal) -> str:
    return f"{format_decimal(value, 2)} EUR"


def format_energy(value: Decimal) -> str:
    return format_decimal(value, 1)


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_unit_price(value: Decimal) -> str:
    return format_decimal(value, 4)


def multiline_text(value: str) -> str:
    return (
        escape(value)
        .replace("\\n", "<br/>")
        .replace("\n", "<br/>")
    )


def validate_invoice(invoice: Invoice) -> None:
    if invoice.status != "finalized":
        raise InvoiceNotFinalizedError(
            "Nur finalisierte Rechnungen können "
            "als PDF erzeugt werden."
        )

    if not invoice.invoice_number:
        raise IncompleteInvoicePdfDataError(
            "Die Rechnungsnummer fehlt."
        )

    if invoice.issue_date is None:
        raise IncompleteInvoicePdfDataError(
            "Das Rechnungsdatum fehlt."
        )

    if invoice.due_date is None:
        raise IncompleteInvoicePdfDataError(
            "Das Zahlungsziel fehlt."
        )

    if not invoice.issuer_name:
        raise IncompleteInvoicePdfDataError(
            "Der Rechnungsaussteller fehlt."
        )

    if not invoice.issuer_address:
        raise IncompleteInvoicePdfDataError(
            "Die Anschrift des Ausstellers fehlt."
        )

    if not invoice.recipient_name:
        raise IncompleteInvoicePdfDataError(
            "Der Rechnungsempfänger fehlt."
        )

    if not invoice.recipient_address:
        raise IncompleteInvoicePdfDataError(
            "Die Anschrift des Empfängers fehlt."
        )

    if not invoice.items:
        raise IncompleteInvoicePdfDataError(
            "Die Rechnung enthält keine Positionen."
        )


class InvoiceCanvas(pdf_canvas.Canvas):
    def __init__(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[
            dict[str, object]
        ] = []

    def showPage(self) -> None:
        self._saved_page_states.append(
            dict(self.__dict__)
        )
        self._startPage()

    def save(self) -> None:
        page_count = len(
            self._saved_page_states
        )

        for page_state in self._saved_page_states:
            self.__dict__.update(page_state)
            self._draw_footer(page_count)
            super().showPage()

        super().save()

    def _draw_footer(
        self,
        page_count: int,
    ) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(
            colors.HexColor("#666666")
        )

        self.drawString(
            18 * mm,
            10 * mm,
            "Elektronisch erstellte Rechnung",
        )

        if page_count > 1:
            self.drawRightString(
                A4[0] - 18 * mm,
                10 * mm,
                (
                    f"Seite {self._pageNumber} "
                    f"von {page_count}"
                ),
            )

        self.restoreState()


def build_invoice_pdf(invoice: Invoice) -> bytes:
    validate_invoice(invoice)

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=invoice.invoice_number,
        author=invoice.issuer_name,
    )

    styles = getSampleStyleSheet()

    body_style = ParagraphStyle(
        "InvoiceBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        spaceAfter=3 * mm,
    )

    small_style = ParagraphStyle(
        "InvoiceSmall",
        parent=body_style,
        fontSize=8,
        leading=10,
    )

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#222222"),
    )

    right_style = ParagraphStyle(
        "InvoiceRight",
        parent=body_style,
        alignment=TA_RIGHT,
    )

    table_header_style = ParagraphStyle(
        "InvoiceTableHeader",
        parent=small_style,
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=7.5,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    story: list[object] = []

    issuer_identifiers: list[str] = []

    if invoice.issuer_tax_number:
        issuer_identifiers.append(
            "Steuernummer: "
            + escape(invoice.issuer_tax_number)
        )

    if invoice.issuer_vat_id:
        issuer_identifiers.append(
            "USt-IdNr.: "
            + escape(invoice.issuer_vat_id)
        )

    issuer_block = Paragraph(
        (
            f"<b>{escape(invoice.issuer_name)}</b><br/>"
            f"{multiline_text(invoice.issuer_address)}"
        ),
        body_style,
    )

    title_block = Paragraph(
        (
            "RECHNUNG<br/>"
            f"<font size='10'>"
            f"{escape(invoice.invoice_number)}"
            "</font>"
        ),
        title_style,
    )

    header_table = Table(
        [[issuer_block, title_block]],
        colWidths=[
            105 * mm,
            69 * mm,
        ],
        hAlign="LEFT",
    )
    header_table.setStyle(
        TableStyle(
            [
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ]
        )
    )

    story.append(header_table)
    story.append(Spacer(1, 12 * mm))

    story.append(
        Paragraph(
            "<b>Rechnung an</b>",
            body_style,
        )
    )

    story.append(
        Paragraph(
            (
                f"{escape(invoice.recipient_name)}<br/>"
                f"{multiline_text(invoice.recipient_address)}"
            ),
            body_style,
        )
    )

    story.append(Spacer(1, 5 * mm))

    metadata = [
        [
            "Rechnungsdatum",
            format_date(invoice.issue_date),
            "Leistungszeitraum",
            (
                format_date(
                    invoice.service_period_start.date()
                )
                + " bis "
                + format_date(
                    invoice.service_period_end.date()
                )
            ),
        ],
        [
            "Rechnungsnummer",
            invoice.invoice_number,
            "Währung",
            invoice.currency,
        ],
    ]

    metadata_table = Table(
        metadata,
        colWidths=[
            35 * mm,
            43 * mm,
            40 * mm,
            56 * mm,
        ],
        hAlign="LEFT",
    )
    metadata_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#EEEEEE"),
                ),
                (
                    "BACKGROUND",
                    (2, 0),
                    (2, -1),
                    colors.HexColor("#EEEEEE"),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (2, 0),
                    (2, -1),
                    "Helvetica-Bold",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#BBBBBB"),
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(metadata_table)
    story.append(Spacer(1, 8 * mm))

    item_rows: list[list[object]] = [
        [
            Paragraph(
                "Pos.",
                table_header_style,
            ),
            Paragraph(
                "Datum",
                table_header_style,
            ),
            Paragraph(
                "WB",
                table_header_style,
            ),
            Paragraph(
                "Gesamt<br/>kWh",
                table_header_style,
            ),
            Paragraph(
                "Netz<br/>kWh",
                table_header_style,
            ),
            Paragraph(
                "PV<br/>kWh",
                table_header_style,
            ),
            Paragraph(
                "Netzpreis<br/>EUR/kWh",
                table_header_style,
            ),
            Paragraph(
                "PV-Preis<br/>EUR/kWh",
                table_header_style,
            ),
            Paragraph(
                "Netto<br/>EUR",
                table_header_style,
            ),
            Paragraph(
                "USt.<br/>%",
                table_header_style,
            ),
            Paragraph(
                "Brutto<br/>EUR",
                table_header_style,
            ),
        ]
    ]

    for item in invoice.items:
        item_rows.append(
            [
                str(item.position_number),
                item.session_start.strftime(
                    "%d.%m.%Y"
                ),
                str(item.station_id),
                format_energy(
                    item.energy_total_kwh
                ),
                format_energy(
                    item.energy_grid_kwh
                ),
                format_energy(
                    item.energy_pv_kwh
                ),
                format_unit_price(
                    item.grid_price_net
                ),
                format_unit_price(
                    item.pv_price_net
                ),
                format_decimal(
                    item.net_amount,
                    2,
                ),
                format_decimal(
                    item.vat_rate,
                    2,
                ),
                format_decimal(
                    item.gross_amount,
                    2,
                ),
            ]
        )

    items_table = LongTable(
        item_rows,
        repeatRows=1,
        colWidths=[
            8 * mm,
            17 * mm,
            15 * mm,
            14 * mm,
            14 * mm,
            14 * mm,
            20 * mm,
            20 * mm,
            18 * mm,
            14 * mm,
            20 * mm,
        ],
        hAlign="LEFT",
    )

    items_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#333333"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (0, 1),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, 0),
                    "CENTER",
                ),
                (
                    "ALIGN",
                    (0, 1),
                    (2, -1),
                    "CENTER",
                ),
                (
                    "ALIGN",
                    (3, 1),
                    (-1, -1),
                    "RIGHT",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F7F7F7"),
                    ],
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#CCCCCC"),
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 8 * mm))

    totals_table = Table(
        [
            [
                "Nettobetrag",
                format_money(invoice.total_net),
            ],
            [
                "Umsatzsteuer",
                format_money(invoice.vat_amount),
            ],
            [
                "Rechnungsbetrag",
                format_money(invoice.total_gross),
            ],
        ],
        colWidths=[
            45 * mm,
            35 * mm,
        ],
        hAlign="RIGHT",
    )

    totals_table.setStyle(
        TableStyle(
            [
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 1),
                    "Helvetica",
                ),
                (
                    "FONTNAME",
                    (0, 2),
                    (-1, 2),
                    "Helvetica-Bold",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, -1),
                    "RIGHT",
                ),
                (
                    "LINEABOVE",
                    (0, 2),
                    (-1, 2),
                    1,
                    colors.HexColor("#333333"),
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
            ]
        )
    )

    payment_term_days = (
        invoice.due_date - invoice.issue_date
    ).days

    if payment_term_days == 0:
        payment_term_text = (
            "Der Betrag ist sofort fällig."
        )
    else:
        payment_term_text = (
            "Der Betrag ist innerhalb von "
            f"{payment_term_days} Tagen ohne "
            "Abzug fällig."
        )

    story.append(totals_table)
    story.append(Spacer(1, 7 * mm))

    story.append(
        Paragraph(
            (
                "<b>Zahlungsbedingung</b><br/>"
                f"{payment_term_text} "
                "Zahlbar bis "
                f"{format_date(invoice.due_date)}."
            ),
            body_style,
        )
    )

    story.append(Spacer(1, 6 * mm))

    if issuer_identifiers:
        story.append(
            Paragraph(
                "<br/>".join(issuer_identifiers),
                small_style,
            )
        )

    story.append(
        Paragraph(
            (
                "Vielen Dank. Bitte bewahren Sie "
                "diese Rechnung für Ihre Unterlagen auf."
            ),
            right_style,
        )
    )

    story.append(Spacer(1, 6 * mm))

    document.build(
        story,
        canvasmaker=InvoiceCanvas,
    )

    return buffer.getvalue()
