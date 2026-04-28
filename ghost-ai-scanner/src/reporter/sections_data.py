# =============================================================
# FILE: src/reporter/sections_data.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Data sections: top offenders, provider breakdown,
#          event log and residual gaps disclosure.
# DEPENDS: reportlab, reporter.styles
# =============================================================

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from .styles import get_styles, DARK_BLUE, WHITE, LIGHT_GRAY, MID_GRAY

S  = get_styles()
SP = lambda n=6: Spacer(1, n)


def top_offenders(offenders: list) -> list:
    """Top offenders ranked by event count."""
    flowables = [
        Paragraph("Top Offenders", S["section"]),
        SP(),
        Paragraph(
            "Sources ranked by unauthorized AI traffic volume during the report period.",
            S["body_muted"]
        ),
        SP(6),
    ]
    data = [["Owner", "Source IP", "Events", "Providers", "Last Seen", "Severity"]]
    for o in offenders[:20]:
        data.append([
            o.get("owner", "—")[:22],
            o.get("src_ip", "—"),
            str(o.get("count", 0)),
            o.get("providers", "—")[:25],
            o.get("last_seen", "—")[:10],
            o.get("severity", "—"),
        ])
    flowables.append(_table(data))
    flowables.append(SP(8))
    return flowables


def provider_breakdown(providers: list) -> list:
    """Provider breakdown ranked by hit count."""
    flowables = [
        Paragraph("Provider Breakdown", S["section"]),
        SP(),
        Paragraph(
            "Unauthorized AI providers accessed during the report period.",
            S["body_muted"]
        ),
        SP(6),
    ]
    data = [["Provider", "Category", "Hit Count", "Unique Sources", "Last Seen"]]
    for p in providers[:30]:
        data.append([
            p.get("provider", "—")[:25],
            p.get("category", "—")[:22],
            str(p.get("count", 0)),
            str(p.get("unique_sources", 0)),
            p.get("last_seen", "—")[:10],
        ])
    flowables.append(_table(data))
    flowables.append(SP(8))
    return flowables


def event_log(events: list) -> list:
    """Full event log — most recent 200 events."""
    flowables = [
        Paragraph("Full Event Log", S["section"]),
        SP(),
        Paragraph(
            f"Showing most recent {min(len(events), 200)} events. "
            "Full log available in S3 findings/ prefix.",
            S["body_muted"]
        ),
        SP(6),
    ]
    data = [["Timestamp", "Owner", "Provider", "Destination", "Severity", "Bytes"]]
    for e in events[:200]:
        data.append([
            str(e.get("timestamp", ""))[:16],
            e.get("owner", e.get("src_ip", "—"))[:18],
            e.get("provider", "—")[:18],
            e.get("dst_domain", e.get("dst_ip", "—"))[:22],
            e.get("severity", "—"),
            str(e.get("bytes_out", 0)),
        ])
    flowables.append(_table(data, small=True))
    flowables.append(SP(8))
    return flowables


def residual_gaps() -> list:
    """Standard residual gaps disclosure — fixed text per report."""
    gaps = [
        ("Fully offline local inference",
         "No network call. CrowdStrike partially mitigates."),
        ("Personal cloud accounts",
         "Personal AWS/GCP, personal credit card. No corporate IAM."),
        ("Web UI manual copy-paste",
         "Browser tab only. Clipboard DLP partially mitigates."),
        ("Personal laptop outside VPN",
         "Device unmanaged. Accepted company risk. Out of scope."),
    ]
    flowables = [
        Paragraph("Residual Gaps", S["section"]),
        SP(),
        Paragraph(
            "The following scenarios are not detectable by any network scanner. "
            "Disclosed here for honest governance reporting.",
            S["body_muted"]
        ),
        SP(6),
    ]
    data = [["Gap", "Why It Escapes", "Status"]]
    for gap, why in gaps:
        data.append([gap, why, "Documented"])
    flowables.append(_table(data))
    return flowables


def _table(data: list, small: bool = False) -> Table:
    """Shared table builder for all data sections."""
    fs  = 7 if small else 8
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), fs),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING",    (0, 0), (-1, 0), 6),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), fs),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    return tbl
