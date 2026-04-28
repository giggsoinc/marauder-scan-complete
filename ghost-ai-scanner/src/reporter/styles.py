# =============================================================
# FILE: src/reporter/styles.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: ReportLab paragraph styles and colour constants.
#          Centralised so every section uses the same design.
#          White background. Corporate palette. Board-ready format.
# DEPENDS: reportlab
# =============================================================

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums  import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.units  import inch

# ── Colour palette ────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1B2A4A")
MID_BLUE    = colors.HexColor("#2E5D9E")
LIGHT_BLUE  = colors.HexColor("#E8F0FB")
GREEN       = colors.HexColor("#00884D")
GREEN_LIGHT = colors.HexColor("#E6F5EE")
ORANGE      = colors.HexColor("#D4680A")
ORANGE_LIGHT= colors.HexColor("#FFF3E0")
RED         = colors.HexColor("#C0392B")
RED_LIGHT   = colors.HexColor("#FDECEA")
GOLD        = colors.HexColor("#8A6D0B")
MUTED       = colors.HexColor("#6C757D")
WHITE       = colors.white
LIGHT_GRAY  = colors.HexColor("#F8F9FA")
MID_GRAY    = colors.HexColor("#DEE2E6")

# Severity colour map
SEVERITY_COLOURS = {
    "CRITICAL": RED,
    "HIGH":     ORANGE,
    "MEDIUM":   GOLD,
    "LOW":      MUTED,
    "UNKNOWN":  colors.HexColor("#6C3483"),
    "CLEAN":    GREEN,
}


def get_styles() -> dict:
    """Build and return all paragraph styles used in the report."""
    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=DARK_BLUE,
            spaceAfter=8,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=14,
            textColor=MID_BLUE,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=WHITE,
            backColor=DARK_BLUE,
            spaceBefore=16,
            spaceAfter=8,
            leftIndent=6,
            rightIndent=6,
            leading=20,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=DARK_BLUE,
            spaceAfter=4,
            leading=13,
        ),
        "body_muted": ParagraphStyle(
            "body_muted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=MUTED,
            spaceAfter=4,
            leading=13,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=WHITE,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=DARK_BLUE,
            alignment=TA_LEFT,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
    }
    return styles
