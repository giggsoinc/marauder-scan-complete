# =============================================================
# FILE: src/reporter/sections_cover.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Cover page and executive summary PDF section builders.
# DEPENDS: reportlab, reporter.styles
# =============================================================

from datetime import date
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.units import inch
from .styles import (
    get_styles, DARK_BLUE, WHITE, LIGHT_GRAY, MID_GRAY, MID_BLUE
)

S  = get_styles()
SP = lambda n=6: Spacer(1, n)


def cover(company: str, date_range: str, classification: str = "CONFIDENTIAL") -> list:
    """Cover page flowables."""
    return [
        SP(60),
        Paragraph("GHOST AI SCANNER", S["subtitle"]),
        Paragraph("Network Audit Report", S["title"]),
        SP(8),
        HRFlowable(width="100%", thickness=4, color=MID_BLUE, spaceAfter=12),
        Paragraph(f"Company: {company}", S["body"]),
        Paragraph(f"Report period: {date_range}", S["body"]),
        Paragraph(f"Generated: {date.today().isoformat()}", S["body"]),
        SP(6),
        Paragraph(f"Classification: {classification}", S["body_muted"]),
        Paragraph(
            "Prepared by Giggso Inc (Ravi Venugopal) · TrinityOps.ai · AIRTaaS",
            S["body_muted"]
        ),
        PageBreak(),
    ]


def executive_summary(summary: dict) -> list:
    """Executive summary section with stats table."""
    total  = summary.get("total_events", 0)
    by_sev = summary.get("by_severity", {})
    crit   = by_sev.get("CRITICAL", 0)
    high   = by_sev.get("HIGH", 0)
    med    = by_sev.get("MEDIUM", 0)

    flowables = [
        Paragraph("Executive Summary", S["section"]),
        SP(),
        Paragraph(
            f"PatronAI detected {total} unauthorized AI traffic events "
            f"during the report period. Of these, {crit} were CRITICAL severity, "
            f"{high} HIGH and {med} MEDIUM. All events logged and routed to Trinity.",
            S["body"]
        ),
        SP(8),
    ]
    data = [
        ["Metric", "Value"],
        ["Total unauthorized events",  str(total)],
        ["Critical severity",          str(crit)],
        ["High severity",              str(high)],
        ["Medium severity",            str(med)],
        ["Unique source IPs",          str(summary.get("unique_sources", 0))],
        ["Unique AI providers",        str(summary.get("unique_providers", 0))],
        ["Alerts fired to Trinity",    str(summary.get("alerts_fired", 0))],
    ]
    flowables.append(_table(data))
    flowables.append(PageBreak())
    return flowables


def _table(data: list) -> Table:
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING",    (0, 0), (-1, 0), 6),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    return tbl
