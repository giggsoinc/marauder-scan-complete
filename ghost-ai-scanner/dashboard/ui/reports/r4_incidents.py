# =============================================================
# FILE: dashboard/ui/reports/r4_incidents.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: R4 — Incident / Findings Export HTML builder.
#          Renders a date-filtered table of ENDPOINT_FINDING
#          events with KPI row and severity badges.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from ._header import filter_by_date, sev_tag, wrap_html

_FINDING_OUTCOMES = {"ENDPOINT_FINDING", "endpoint_finding"}
_MAX_ROWS = 300


def _kpi_card(value: str, label: str, extra_cls: str = "") -> str:
    """Return a single KPI card HTML fragment."""
    return (
        f'<div class="kc {extra_cls}">'
        f'<div class="kv">{value}</div>'
        f'<div class="kl">{label}</div>'
        f"</div>"
    )


def _findings_table(events: list) -> str:
    """Build the all-findings HTML table (max _MAX_ROWS rows)."""
    rows = ""
    for e in events[:_MAX_ROWS]:
        ts = (e.get("timestamp") or "")[:19]
        user = e.get("email") or e.get("owner") or "—"
        dev = (e.get("device_id") or e.get("src_hostname") or e.get("src_ip") or "—")[:30]
        prov = (e.get("provider") or "—")[:50]
        cat = e.get("category") or "—"
        sev = (e.get("severity") or "LOW").upper()
        geo = e.get("geo_country") or "—"
        rows += (
            f"<tr><td>{ts}</td><td>{user}</td><td>{dev}</td>"
            f"<td>{prov}</td><td>{cat}</td>"
            f"<td>{sev_tag(sev)}</td><td>{geo}</td></tr>"
        )
    truncated = ""
    if len(events) > _MAX_ROWS:
        truncated = (
            f'<div class="vb">Showing first {_MAX_ROWS} of '
            f"{len(events)} findings. Export full data via API.</div>"
        )
    header = (
        "<tr><th>TIMESTAMP</th><th>USER</th><th>DEVICE</th>"
        "<th>PROVIDER</th><th>CATEGORY</th><th>SEV</th><th>GEO</th></tr>"
    )
    return f"{truncated}<table>{header}{rows}</table>"


def build_html(
    events: list,
    d_from: str,
    d_to: str,
    admin_email: str,
    company: str,
    logo_b64: str,
) -> str:
    """Build complete R4 Incident / Findings HTML report.

    Args:
        events:      Raw event dicts from the PatronAI pipeline.
        d_from:      Start date string YYYY-MM-DD (inclusive).
        d_to:        End date string YYYY-MM-DD (inclusive).
        admin_email: Report requester email shown in header.
        company:     Tenant company name shown in header.
        logo_b64:    Base-64 encoded PNG logo (may be empty string).

    Returns:
        Complete HTML document as a string.
    """
    try:
        filtered = filter_by_date(events, d_from, d_to)
    except Exception as exc:
        import sys
        print(f"[r4] filter_by_date error: {exc}", file=sys.stderr)
        filtered = list(events)

    findings = [
        e for e in filtered
        if (e.get("outcome") or "") in _FINDING_OUTCOMES
    ]
    findings.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    total = len(findings)
    crit = sum(1 for e in findings if (e.get("severity") or "").upper() == "CRITICAL")
    high = sum(1 for e in findings if (e.get("severity") or "").upper() == "HIGH")
    users = len({e.get("email") or e.get("owner") for e in findings} - {None, ""})

    kpi = (
        '<div class="kr">'
        + _kpi_card(str(total), "Total Findings")
        + _kpi_card(str(crit), "Critical", "crit")
        + _kpi_card(str(high), "High", "high")
        + _kpi_card(str(users), "Unique Users")
        + "</div>"
    )

    table_section = (
        '<div class="sec">'
        '<div class="st">All Findings</div>'
        + _findings_table(findings)
        + "</div>"
    )

    body = kpi + table_section
    return wrap_html(
        "Incident / Findings Report",
        body,
        company,
        d_from,
        d_to,
        admin_email,
        logo_b64,
    )
