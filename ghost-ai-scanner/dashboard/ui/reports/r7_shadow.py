# =============================================================
# FILE: dashboard/ui/reports/r7_shadow.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: R7 — Shadow AI / Provider Census HTML builder.
#          One row per unique provider across the org; shows
#          user reach, device reach, first/last seen, max severity.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import sys
from collections import Counter
from ._header import filter_by_date, max_sev, sev_tag, wrap_html

_FINDING_OUTCOMES = {"ENDPOINT_FINDING", "endpoint_finding"}


def _dev_key(e: dict) -> str:
    """Return the best available device identifier for an event."""
    return e.get("device_id") or e.get("src_hostname") or e.get("src_ip") or "unknown"


def _kpi(value: str, label: str, cls: str = "") -> str:
    """Return a single KPI card HTML fragment."""
    return (f'<div class="kc {cls}"><div class="kv">{value}</div>'
            f'<div class="kl">{label}</div></div>')


def _build_census(findings: list) -> list[dict]:
    """Aggregate findings into one record per unique provider.

    Returns list of dicts sorted by user count descending.
    """
    census: dict[str, dict] = {}
    for e in findings:
        prov = (e.get("provider") or "unknown").strip()
        if prov not in census:
            census[prov] = {
                "user_set": set(), "device_set": set(),
                "first": None, "last": None,
                "events": [], "cats": Counter(),
            }
        c = census[prov]
        user = e.get("email") or e.get("owner") or ""
        if user:
            c["user_set"].add(user)
        c["device_set"].add(_dev_key(e))
        ts10 = (e.get("timestamp") or "")[:10]
        if ts10:
            c["first"] = min(c["first"] or ts10, ts10)
            c["last"] = max(c["last"] or ts10, ts10)
        c["events"].append(e)
        cat = e.get("category") or ""
        if cat:
            c["cats"][cat] += 1

    rows = []
    for info in census.values():
        rows.append({
            "provider": (info["events"][0].get("provider") or "unknown").strip(),
            "user_count": len(info["user_set"]),
            "device_count": len(info["device_set"]),
            "first_seen": info["first"] or "—",
            "last_seen": info["last"] or "—",
            "max_sev": max_sev(info["events"]),
            "category": info["cats"].most_common(1)[0][0] if info["cats"] else "—",
        })
    rows.sort(key=lambda r: r["user_count"], reverse=True)
    return rows


def build_html(events: list, d_from: str, d_to: str,
               admin_email: str, company: str, logo_b64: str) -> str:
    """Build complete R7 Shadow AI Provider Census HTML report.

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
        print(f"[r7] filter_by_date: {exc}", file=sys.stderr)
        filtered = list(events)

    findings = [e for e in filtered if (e.get("outcome") or "") in _FINDING_OUTCOMES]
    census = _build_census(findings)

    u_prov = len(census)
    u_users = len({e.get("email") or e.get("owner") for e in findings} - {None, ""})
    u_dev = len({_dev_key(e) for e in findings})
    crit = sum(1 for r in census if r["max_sev"] == "CRITICAL")

    kpi = ('<div class="kr">'
           + _kpi(str(u_prov), "Unique Providers")
           + _kpi(str(u_users), "Total Users")
           + _kpi(str(u_dev), "Unique Devices")
           + _kpi(str(crit), "Critical Providers", "crit" if crit else "")
           + "</div>")

    # V1: no approved-provider list — all detections are unapproved shadow AI
    summary = (f'<div class="vb"><strong>{u_prov} provider(s) detected — none on approved list.'
                f'</strong> <span style="font-size:9px">'
                f"(V1: approved-provider list not yet configured. "
                f"All detections treated as unapproved shadow AI.)</span></div>")

    rows = ""
    for r in census:
        rows += (f"<tr><td>{r['provider']}</td><td>{r['category']}</td>"
                 f"<td>{r['user_count']}</td><td>{r['device_count']}</td>"
                 f"<td>{r['first_seen']}</td><td>{r['last_seen']}</td>"
                 f"<td>{sev_tag(r['max_sev'])}</td></tr>")
    tbl = ('<div class="sec"><div class="st">Provider Census</div>'
           "<table><tr><th>PROVIDER</th><th>CATEGORY</th><th>USERS</th>"
           f"<th>DEVICES</th><th>FIRST SEEN</th><th>LAST SEEN</th><th>MAX SEV</th></tr>"
           f"{rows}</table></div>")

    return wrap_html("Shadow AI / Provider Census",
                     kpi + summary + tbl,
                     company, d_from, d_to, admin_email, logo_b64)
