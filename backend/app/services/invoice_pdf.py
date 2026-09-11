from datetime import date
from decimal import Decimal
from html import escape
from io import BytesIO
from functools import partial

from reportlab.lib import colors
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.barcode.qrencoder import QR8bitByte
from reportlab.graphics.shapes import Drawing, Group, Rect, String
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas as pdf_canvas

from app.models.invoice import Invoice
from app.services.invoice_girocode import (
    GirocodeError,
    build_girocode_payload,
)

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


def format_iban_display(value: str) -> str:
    # Nur für die Anzeige: Gruppierung in 4er-Blöcken
    # (übliche IBAN-Schreibweise). Der für den Girocode
    # verwendete Rohwert bleibt davon unberührt.
    compact = "".join(value.split())

    return " ".join(
        compact[i : i + 4]
        for i in range(0, len(compact), 4)
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


def build_invoice_pdf(
    invoice: Invoice,
    *,
    girocode_enabled: bool = False,
    issuer_email: str | None = None,
) -> bytes:
    validate_invoice(invoice)

    girocode = None
    girocode_label = None
    if (
        girocode_enabled
        and invoice.document_type != "cancellation"
        and invoice.total_gross > 0
    ):
        try:
            payload = build_girocode_payload(
                beneficiary=invoice.issuer_name,
                iban=invoice.issuer_iban,
                bic=invoice.issuer_bic,
                amount=invoice.total_gross,
                reference=invoice.invoice_number,
                currency=invoice.currency,
            )
        except GirocodeError as exc:
            raise InvoicePdfError(str(exc)) from exc

        # Force UTF-8 byte mode and EPC error level M. The 331-byte
        # payload limit fits QR version 13; reserve four quiet modules.
        # Rendered at 75% of the original 40mm size.
        code_size = 30 * mm
        girocode = Drawing(code_size, code_size)
        girocode.add(Rect(
            0, 0, code_size, code_size,
            fillColor=colors.white,
            strokeColor=None,
        ))
        girocode.add(QrCodeWidget(
            [QR8bitByte(payload.encode("utf-8"))],
            barLevel="M",
            barBorder=4,
            barWidth=code_size,
            barHeight=code_size,
        ))

        # "Girocode" rotated 90° (reading bottom-to-top), rendered as a
        # standalone strip that sits flush against the QR code's left
        # edge with no gap in between.
        girocode_label_font = "Helvetica"
        girocode_label_size = 9
        girocode_label_text = "Girocode"
        girocode_label_len = stringWidth(
            girocode_label_text, girocode_label_font, girocode_label_size,
        )
        girocode_label_thickness = girocode_label_size + 4

        # The string is positioned so that, after the 90° rotation,
        # its right-hand edge (descent side) lands exactly on the
        # right edge of this box — i.e. flush against the QR code's
        # own left edge, with no unused space in between.
        girocode_label = Drawing(girocode_label_thickness, code_size)
        label_string = String(
            (code_size - girocode_label_len) / 2,
            -girocode_label_thickness,
            girocode_label_text,
            fontName=girocode_label_font,
            fontSize=girocode_label_size,
            fillColor=colors.black,
        )
        label_group = Group(label_string)
        label_group.rotate(90)
        girocode_label.add(label_group)

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

    header_title_style = ParagraphStyle(
        "InvoiceHeaderTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=colors.HexColor("#222222"),
    )

    right_style = ParagraphStyle(
        "InvoiceRight",
        parent=body_style,
        alignment=TA_RIGHT,
    )

    right_small_style = ParagraphStyle(
        "InvoiceRightSmall",
        parent=right_style,
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

    header_title_text = (
        "Ladestromrechnung – Storno"
        if is_cancellation
        else "Ladestromrechnung"
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

    if invoice.document_type != "cancellation":
        bank_details: list[str] = []

        if invoice.issuer_bank_name:
            bank_details.append(
                escape(invoice.issuer_bank_name)
            )

        if invoice.issuer_iban:
            bank_details.append(
                "IBAN: "
                + escape(
                    format_iban_display(
                        invoice.issuer_iban
                    )
                )
            )

        if invoice.issuer_bic:
            bank_details.append(
                "BIC: "
                + escape(invoice.issuer_bic)
            )

        if bank_details:
            issuer_identifiers.append(
                "<b>Bankverbindung:</b> "
                + " | ".join(bank_details)
            )

    # --- Right header block: issuer identity -----------------------
    # Name + Anschrift (+ Telefon, falls konfiguriert, + E-Mail,
    # falls konfiguriert), kleiner Absatz, Steuernummer/USt-IdNr.,
    # kleiner Absatz, IBAN/BIC (nur bei Rechnungen, nicht bei
    # Storno).
    normalized_issuer_email = (
        issuer_email.strip()
        if issuer_email
        else None
    )

    right_cell_items: list[object] = [
        Paragraph(
            (
                f"<b>{escape(invoice.issuer_name)}</b><br/>"
                f"{multiline_text(invoice.issuer_address)}"
                + (
                    "<br/>Tel.: "
                    + escape(invoice.issuer_phone)
                    if invoice.issuer_phone
                    else ""
                )
                + (
                    "<br/>"
                    + escape(normalized_issuer_email)
                    if normalized_issuer_email
                    else ""
                )
            ),
            right_style,
        )
    ]

    tax_lines: list[str] = []

    if invoice.issuer_tax_number:
        tax_lines.append(
            "Steuernummer: "
            + escape(invoice.issuer_tax_number)
        )

    if invoice.issuer_vat_id:
        tax_lines.append(
            "USt-IdNr.: "
            + escape(invoice.issuer_vat_id)
        )

    if tax_lines:
        right_cell_items.append(Spacer(1, 1 * mm))
        right_cell_items.append(
            Paragraph(
                "<br/>".join(tax_lines),
                right_small_style,
            )
        )

    bank_lines: list[str] = []

    if not is_cancellation:
        if invoice.issuer_iban:
            bank_lines.append(
                "IBAN: "
                + escape(
                    format_iban_display(
                        invoice.issuer_iban
                    )
                )
            )

        if invoice.issuer_bic:
            bank_lines.append(
                "BIC: "
                + escape(invoice.issuer_bic)
            )

    if bank_lines:
        right_cell_items.append(Spacer(1, 1 * mm))
        right_cell_items.append(
            Paragraph(
                "<br/>".join(bank_lines),
                right_small_style,
            )
        )

    # --- Left header block: title + recipient address --------------
    # Die Empfängeradresse wird so plaziert, dass sie im
    # Sichtfenster eines Fensterkuverts (DIN 5008 Form A, Fenster ab
    # ca. 45mm Blattoberkante) erscheint.
    title_block = Paragraph(
        escape(header_title_text),
        header_title_style,
    )

    recipient_block = Paragraph(
        (
            f"<b>{escape(invoice.recipient_name)}<br/>"
            f"{multiline_text(invoice.recipient_address)}</b>"
        ),
        body_style,
    )

    header_col_widths = [95 * mm, 79 * mm]

    _, title_height = title_block.wrap(
        header_col_widths[0],
        1000 * mm,
    )

    recipient_window_top = 45 * mm
    recipient_offset = (
        recipient_window_top - document.topMargin
    )
    recipient_spacer_height = max(
        2 * mm,
        recipient_offset - title_height,
    )

    left_cell_items: list[object] = [
        title_block,
        Spacer(1, recipient_spacer_height),
        recipient_block,
    ]

    header_table = Table(
        [[left_cell_items, right_cell_items]],
        colWidths=header_col_widths,
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
    story.append(Spacer(1, 10 * mm))

    # --- Full-width metadata row -------------------------------------
    # Kein Kasten/Grid mehr: pro Feld eine kleine, rechtsbündige
    # Überschrift, darunter fett der Feldinhalt.
    service_period_text = (
        format_date(
            invoice.service_period_start.date()
        )
        + " – "
        + format_date(
            invoice.service_period_end.date()
        )
    )

    meta_label_style = ParagraphStyle(
        "InvoiceMetaLabel",
        parent=small_style,
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#666666"),
        spaceAfter=0,
    )

    meta_label_right_style = ParagraphStyle(
        "InvoiceMetaLabelRight",
        parent=meta_label_style,
        alignment=TA_RIGHT,
    )

    meta_value_style = ParagraphStyle(
        "InvoiceMetaValue",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=12.5,
        alignment=TA_LEFT,
        spaceAfter=0,
    )

    meta_value_right_style = ParagraphStyle(
        "InvoiceMetaValueRight",
        parent=meta_value_style,
        alignment=TA_RIGHT,
    )

    def meta_field(
        label: str,
        value: str,
        *,
        align_right: bool = False,
    ) -> list[object]:
        return [
            Paragraph(
                escape(label),
                (
                    meta_label_right_style
                    if align_right
                    else meta_label_style
                ),
            ),
            Paragraph(
                escape(value),
                (
                    meta_value_right_style
                    if align_right
                    else meta_value_style
                ),
            ),
        ]

    metadata_col_widths = [
        58 * mm,
        58 * mm,
        58 * mm,
    ]

    metadata = [
        [
            meta_field(
                document_number_label,
                invoice.invoice_number,
            ),
            meta_field(
                "Leistungszeitraum",
                service_period_text,
            ),
            meta_field(
                issue_date_label,
                format_date(invoice.issue_date),
                align_right=True,
            ),
        ],
    ]

    metadata_style_commands = [
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
            4 * mm,
        ),
    ]

    if is_cancellation:
        original_number = (
            invoice.original_invoice.invoice_number
            if invoice.original_invoice is not None
            else None
        )

        metadata.append(
            [
                meta_field(
                    "Originalrechnung",
                    original_number or "-",
                ),
                meta_field(
                    "Stornierungsgrund",
                    invoice.cancellation_reason or "-",
                ),
                "",
            ]
        )

        metadata_style_commands.append(
            (
                "SPAN",
                (1, 1),
                (2, 1),
            )
        )

    metadata_table = Table(
        metadata,
        colWidths=metadata_col_widths,
        hAlign="LEFT",
    )
    metadata_table.setStyle(
        TableStyle(metadata_style_commands)
    )

    story.append(metadata_table)

    # --- Optional Hinweis-Zeile aus den RFID-Kartenzuordnungen ------
    # Zeigt z.B. Zuordnungsmerkmale wie ein Kfz-Kennzeichen, die bei
    # der jeweiligen Ladekarten-Zuordnung hinterlegt wurden.
    assignment_notes: list[str] = []
    seen_assignment_notes: set[str] = set()

    for item in invoice.items:
        charging_session = getattr(
            item,
            "charging_session",
            None,
        )

        if charging_session is None:
            continue

        rfid_assignment = getattr(
            charging_session,
            "rfid_assignment",
            None,
        )

        if rfid_assignment is None:
            continue

        note = rfid_assignment.note

        if not note:
            continue

        normalized_note = note.strip()

        if (
            not normalized_note
            or normalized_note
            in seen_assignment_notes
        ):
            continue

        seen_assignment_notes.add(normalized_note)
        assignment_notes.append(normalized_note)

    if assignment_notes:
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                (
                    "<b>Hinweis:</b> "
                    + "<br/>".join(
                        escape(note)
                        for note in assignment_notes
                    )
                ),
                small_style,
            )
        )

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

    flat_fee_row_indices: list[int] = []

    for item in invoice.items:
        if item.item_type in {
            "monthly_base_fee",
            "postal_delivery",
        }:
            flat_fee_row_indices.append(
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

    for row_index in flat_fee_row_indices:
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
                "(bis "
                f"{format_date(invoice.due_date)}"
                ") ohne Abzug fällig."
            )
        else:
            payment_text = (
                "Der Rechnungsbetrag ist innerhalb "
                f"von {payment_term_days} Tagen "
                "(bis "
                f"{format_date(invoice.due_date)}"
                ") ohne Abzug fällig."
            )

    payment_details: list[object] = [
        Paragraph(
            (
                f"<b>{payment_heading}</b><br/>"
                f"{payment_text}"
            ),
            body_style,
        ),
        Spacer(1, 6 * mm),
    ]

    if issuer_identifiers:
        payment_details.append(
            Paragraph(
                "<br/>".join(issuer_identifiers),
                body_style,
            )
        )

    if girocode is not None:
        caption_style = ParagraphStyle(
            "GirocodeCaption",
            parent=small_style,
            alignment=TA_CENTER,
        )

        girocode_group_width = girocode_label_thickness + code_size

        # Row 1: label and QR code flush against each other, no gap.
        # Row 2: caption, centered under the QR code column only (not
        # under the label column), with a small gap above it.
        girocode_group = Table(
            [
                [girocode_label, girocode],
                [
                    "",
                    Paragraph(
                        "Für Ihre Banking-App",
                        caption_style,
                    ),
                ],
            ],
            colWidths=[girocode_label_thickness, code_size],
            hAlign="LEFT",
        )
        girocode_group.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, 0), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
            ("TOPPADDING", (0, 1), (-1, 1), 2 * mm),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
        ]))

        payment_table = Table(
            [[payment_details, girocode_group]],
            colWidths=[
                CONTENT_WIDTH - girocode_group_width,
                girocode_group_width,
            ],
            hAlign="LEFT",
        )
        payment_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether([
            totals_table,
            Spacer(1, 7 * mm),
            payment_table,
        ]))
    else:
        story.append(totals_table)
        story.append(Spacer(1, 7 * mm))
        story.extend(payment_details)

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
