from datetime import date
from decimal import Decimal
from html import escape
from io import BytesIO
from functools import partial

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

    if (
        invoice.document_type == "invoice"
        and invoice.due_date is None
    ):
        raise InvoicePdfError(
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
        is_cancellation: bool = False,
        **kwargs: object,
    ) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self.is_cancellation = is_cancellation
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
    
        footer_document_label = (
            "Elektronisch erstellter Stornobeleg"
            if self.is_cancellation
            else "Elektronisch erstellte Rechnung"
        )
        self.drawString(
            18 * mm,
            10 * mm,
            footer_document_label,
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

    is_cancellation = (
        invoice.document_type == "cancellation"
    )

    document_title = (
        "STORNORECHNUNG"
        if is_cancellation
        else "RECHNUNG"
    )

    recipient_heading = (
        "Stornorechnung an"
        if is_cancellation
        else "Rechnung an"
    )

    issue_date_label = (
        "Stornodatum"
        if is_cancellation
        else "Rechnungsdatum"
    )

    document_number_label = (
        "Stornonummer"
        if is_cancellation
        else "Rechnungsnummer"
    )

    total_label = (
        "Stornobetrag"
        if is_cancellation
        else "Rechnungsbetrag"
    )

    payment_heading = (
        "Hinweis"
        if is_cancellation
        else "Zahlungsbedingung"
    )

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

    title_font_size = (
        16
        if is_cancellation
        else 20
    )

    title_block = Paragraph(
        (
            f"<font size='{title_font_size}'>"
            f"{document_title}"
            "</font><br/>"
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
            f"<b>{recipient_heading}</b>",
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
            issue_date_label,
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
            document_number_label,
            invoice.invoice_number,
            "Währung",
            invoice.currency,
        ],
    ]

    if is_cancellation:
        original_number = (
            invoice.original_invoice.invoice_number
            if invoice.original_invoice is not None
            else None
        )

        metadata.append(
            [
                "Originalrechnung",
                original_number or "-",
                "Stornierungsgrund",
                invoice.cancellation_reason or "-",
            ]
        )

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

    base_fee_row_indices: list[int] = []

    for item in invoice.items:
        if item.item_type == "monthly_base_fee":
            base_fee_row_indices.append(
                len(item_rows)
            )

            item_rows.append(
                [
                    str(item.position_number),
                    Paragraph(
                        multiline_text(
                            item.description
                        ),
                        body_style,
                    ),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
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
            continue

        if item.item_type != "charging_session":
            raise IncompleteInvoicePdfDataError(
                "Die Rechnungsposition "
                f"{item.id} besitzt den "
                f"unbekannten Typ "
                f"{item.item_type!r}."
            )

        if any(
            value is None
            for value in (
                item.session_start,
                item.station_id,
                item.energy_total_kwh,
                item.energy_grid_kwh,
                item.energy_pv_kwh,
                item.grid_price_net,
                item.pv_price_net,
            )
        ):
            raise IncompleteInvoicePdfDataError(
                "Für die Ladeposition "
                f"{item.id} fehlen "
                "abrechnungsrelevante Daten."
            )

        item_rows.append(
            [
                str(item.position_number),
                item.session_start.strftime(
                    "%d.%m.%Y"
                ),
                item.station_id,
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

    for row_index in base_fee_row_indices:
        items_table.setStyle(
            TableStyle(
                [
                    (
                        "SPAN",
                        (1, row_index),
                        (7, row_index),
                    ),
                    (
                        "ALIGN",
                        (1, row_index),
                        (7, row_index),
                        "LEFT",
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
                total_label,
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

    if invoice.document_type == "cancellation":
        payment_text = (
            "Dieser Stornobeleg hebt die "
            "zugehörige Rechnung vollständig auf. "
            "Für den Stornobeleg besteht kein "
            "Zahlungsziel."
        )
    else:
        if invoice.due_date is None:
            raise InvoicePdfError(
                "Das Zahlungsziel fehlt."
            )

        payment_term_days = (
            invoice.due_date - invoice.issue_date
        ).days

        if payment_term_days == 0:
            payment_text = (
                "Der Rechnungsbetrag ist sofort "
                "ohne Abzug fällig.<br/>"
                "Zahlbar bis "
                f"{format_date(invoice.due_date)}."
            )
        else:
            payment_text = (
                "Der Rechnungsbetrag ist innerhalb "
                f"von {payment_term_days} Tagen "
                "ohne Abzug fällig.<br/>"
                "Zahlbar bis "
                f"{format_date(invoice.due_date)}."
            )

    story.append(totals_table)
    story.append(Spacer(1, 7 * mm))

    story.append(
        Paragraph(
            (
                f"<b>{payment_heading}</b><br/>"
                f"{payment_text}"
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

    footer_text = (
        (
            "Bitte bewahren Sie diesen Stornobeleg "
            "zusammen mit der Originalrechnung auf."
        )
        if is_cancellation
        else (
            "Vielen Dank. Bitte bewahren Sie diese "
            "Rechnung für Ihre Unterlagen auf."
        )
    )

    story.append(
        Paragraph(
            footer_text,
            body_style,
        )
    )

    story.append(Spacer(1, 6 * mm))

    document.build(
        story,
        canvasmaker=partial(
            InvoiceCanvas,
            is_cancellation=is_cancellation,
        ),
    )

    return buffer.getvalue()
