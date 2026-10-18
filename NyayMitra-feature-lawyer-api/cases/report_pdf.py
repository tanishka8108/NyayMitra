"""PDF generation for NyayMitra's unified case summary."""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NOT_AVAILABLE = "Not available in the record."


def _text(value):
    """Return escaped, printable text without inventing missing values."""
    if value is None or not str(value).strip():
        return NOT_AVAILABLE
    return escape(str(value).strip())


def _paragraph(value, style):
    return Paragraph(_text(value), style)


def _section(title, styles, story):
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(escape(title), styles["Heading2"]))
    story.append(Spacer(1, 2 * mm))


def _table(rows, widths, styles, header=True):
    wrapped = []
    for row_index, row in enumerate(rows):
        style = styles["table_header"] if header and row_index == 0 else styles["BodyText"]
        wrapped.append([Paragraph(_text(cell), style) for cell in row])

    table = Table(wrapped, colWidths=widths, repeatRows=1 if header else 0)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DCE2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F6"))
        if header else ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    return table


def build_case_summary_pdf(record, data_source):
    """Build a PDF using only the supplied case record and provenance."""
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="NyayMitra Unified Case Summary",
        author="NyayMitra",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#23395B"),
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="table_header",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
    ))
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12

    story = [
        Paragraph("NyayMitra — Unified Case Summary", styles["ReportTitle"]),
        Paragraph(
            "Generated on " + escape(datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")),
            styles["Normal"],
        ),
        Spacer(1, 4 * mm),
    ]

    _section("1. Case overview", styles, story)
    overview = [
        ["Field", "Recorded value"],
        ["CNR", record.get("cnr_number")],
        ["Case type", record.get("case_type")],
        ["Status", record.get("case_status")],
        ["Current stage", record.get("current_case_stage")],
        ["Filing number", record.get("filing_number")],
        ["Filing date", record.get("filing_date")],
        ["Registration number", record.get("registration_number")],
        ["Registration date", record.get("registration_date")],
        ["First hearing", record.get("first_hearing_date")],
        ["Next hearing", record.get("next_hearing_date")],
    ]
    story.append(_table(
        overview,
        [48 * mm, 120 * mm],
        styles,
    ))

    _section("2. Parties and court", styles, story)
    parties = [
        ["Field", "Recorded value"],
        ["Petitioner", record.get("petitioner_name")],
        ["Respondents", ", ".join(record.get("respondents_list") or []) or None],
        ["Petitioner's advocate", record.get("petitioner_advocate")],
        ["Court", record.get("court_name")],
        ["District", record.get("court_district")],
        ["State", record.get("court_state")],
        ["Presiding judge", record.get("presiding_judge")],
        ["Applied act", record.get("applied_act")],
        ["Applied section", record.get("applied_section")],
    ]
    story.append(_table(parties, [48 * mm, 120 * mm], styles))

    _section("3. Case timeline", styles, story)
    timeline = record.get("timeline") or []
    if timeline:
        rows = [["Date", "Event", "Details"]]
        for event in timeline:
            rows.append([
                event.get("date") or NOT_AVAILABLE,
                event.get("event") or NOT_AVAILABLE,
                event.get("description") or event.get("purpose") or NOT_AVAILABLE,
            ])
        story.append(_table(rows, [30 * mm, 43 * mm, 95 * mm], styles))
    else:
        story.append(Paragraph(
            "No timeline events are available in this record.",
            styles["BodyText"],
        ))

    _section("4. Available court orders", styles, story)
    orders = record.get("orders") or []
    if orders:
        rows = [["Date", "Type / number", "Details"]]
        for order in orders:
            kind = order.get("order_type") or "Order"
            number = order.get("order_number")
            label = f"{kind} — {number}" if number else kind
            details = order.get("order_details") or order.get("order_section")
            rows.append([
                order.get("order_date") or NOT_AVAILABLE,
                label,
                details or NOT_AVAILABLE,
            ])
        story.append(_table(rows, [30 * mm, 43 * mm, 95 * mm], styles))
    else:
        story.append(Paragraph(
            "No court orders are included in the available record. "
            "This does not establish that no orders exist.",
            styles["BodyText"],
        ))

    _section("5. Data availability", styles, story)
    missing = []
    for label, key in (
        ("Case status", "case_status"),
        ("Filing date", "filing_date"),
        ("Registration date", "registration_date"),
        ("Next hearing date", "next_hearing_date"),
        ("Court name", "court_name"),
        ("Petitioner name", "petitioner_name"),
    ):
        if not record.get(key) or not str(record.get(key)).strip():
            missing.append(label)

    if missing:
        story.append(Paragraph(
            "The following fields are missing: " + escape(", ".join(missing)) + ".",
            styles["BodyText"],
        ))
    else:
        story.append(Paragraph(
            "The listed key fields are present in the supplied record. "
            "Their current accuracy has not been independently verified.",
            styles["BodyText"],
        ))

    source = data_source or {}
    source_label = source.get("label") or source.get("provider") or "Unknown"
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "<b>Data source:</b> " + escape(str(source_label)),
        styles["BodyText"],
    ))
    story.append(Paragraph(
        escape(str(source.get("disclaimer") or
                   "The source and freshness of this record could not be verified.")),
        styles["BodyText"],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "<b>Important:</b> This is a generated case summary, not a certified "
        "court document or a substitute for legal advice. Verify dates, orders, "
        "and current status with the official court record or a qualified advocate.",
        styles["BodyText"],
    ))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#606A78"))
        canvas.drawString(18 * mm, 10 * mm, "NyayMitra • Case summary")
        canvas.drawRightString(
            A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}"
        )
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
