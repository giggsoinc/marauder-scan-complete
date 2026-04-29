# =============================================================
# FILE: dashboard/ui/reports/r3_user.py
# VERSION: 1.0.0 / UPDATED: 2026-04-28 / OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: R3 — Per-user Risk Report HTML builder.
#          Profile KPIs, AI footprint table, org comparison.
# AUDIT LOG: v1.0.0 2026-04-28 Initial.
# =============================================================

from collections import defaultdict
from . import _header


def _dedup_footprint(evts: list) -> list:
    """Dedup to latest event per (category, provider) key."""
    seen: dict = {}
    for e in evts:
        key = (e.get("category") or "", e.get("provider") or "")
        ts = e.get("timestamp") or ""
        if key not in seen or ts > (seen[key].get("timestamp") or ""):
            seen[key] = e
    return list(seen.values())


def _kpi_card(value: str, label: str, extra_cls: str = "") -> str:
    """Render a single KPI card."""
    cls = f"kc {extra_cls}".strip()
    return (f'<div class="{cls}"><div class="kv">{value}</div>'
            f'<div class="kl">{label}</div></div>')


def _org_avg_providers(all_events: list) -> float:
    """Compute average unique providers per user across all events."""
    user_providers: dict = defaultdict(set)
    for e in all_events:
        user = e.get("email") or e.get("owner") or ""
        prov = e.get("provider") or ""
        if user and prov:
            user_providers[user].add(prov)
    if not user_providers:
        return 0.0
    total = sum(len(v) for v in user_providers.values())
    return round(total / len(user_providers), 1)


def build_html(events: list, d_from: str, d_to: str,
               admin_email: str, company: str, logo_b64: str,
               target_email: str = "") -> str:
    """Build Per-User Risk Report HTML string for target_email."""
    if not target_email:
        body = '<div class="gb">No target user specified. Please select a user.</div>'
        return _header.wrap_html(
            "User Risk Report", body, company, d_from, d_to, admin_email, logo_b64
        )

    user_evts = [
        e for e in events
        if (e.get("email") or "").lower() == target_email.lower()
        or (e.get("owner") or "").lower() == target_email.lower()
    ]
    ranged = _header.filter_by_date(user_evts, d_from, d_to)
    findings = [e for e in ranged if e.get("outcome") == "ENDPOINT_FINDING"]

    if not findings:
        body = f'<div class="ok">No findings for <strong>{target_email}</strong> in this period.</div>'
        return _header.wrap_html(
            f"User Risk Report — {target_email}", body,
            company, d_from, d_to, admin_email, logo_b64
        )

    footprint = _dedup_footprint(findings)
    unique_providers = {e.get("provider") for e in findings} - {"", None}
    unique_devices = {e.get("device_id") for e in findings} - {"", None}
    top_sev = _header.max_sev(findings)
    sev_cls = "crit" if top_sev == "CRITICAL" else ("high" if top_sev == "HIGH" else "")

    kpi_row = (
        '<div class="kr">'
        + _kpi_card(str(len(findings)), "Total Events")
        + _kpi_card(str(len(unique_providers)), "Unique Providers")
        + _kpi_card(top_sev, "Highest Severity", sev_cls)
        + _kpi_card(str(len(unique_devices)), "Unique Devices")
        + "</div>"
    )

    fp_rows = "".join(
        "<tr>"
        f"<td>{e.get('category') or '—'}</td>"
        f"<td>{e.get('provider') or '—'}</td>"
        f"<td>{(e.get('timestamp') or '')[:10] or '—'}</td>"
        f"<td>{_header.sev_tag(e.get('severity') or 'LOW')}</td>"
        "</tr>"
        for e in footprint
    )
    fp_tbl = ("<table><tr><th>CATEGORY</th><th>PROVIDER</th>"
              "<th>LAST SEEN</th><th>SEV</th></tr>" + fp_rows + "</table>")

    org_avg = _org_avg_providers(events)
    user_cnt = len(unique_providers)
    cmp_cls = "gb" if user_cnt > org_avg * 1.5 else "ok"
    cmp_box = (f'<div class="{cmp_cls}">'
               f'This user: <strong>{user_cnt} provider{"s" if user_cnt != 1 else ""}</strong>'
               f' &nbsp;·&nbsp; Org avg: <strong>{org_avg}</strong></div>')

    last10 = sorted(findings, key=lambda e: e.get("timestamp") or "", reverse=True)[:10]
    hist_rows = "".join(
        "<tr>"
        f"<td>{(e.get('timestamp') or '')[:16]}</td>"
        f"<td>{e.get('provider') or '—'}</td>"
        f"<td>{e.get('category') or '—'}</td>"
        f"<td>{_header.sev_tag(e.get('severity') or 'LOW')}</td>"
        f"<td>{e.get('device_id') or '—'}</td>"
        "</tr>"
        for e in last10
    )
    hist_tbl = ("<table><tr><th>TIMESTAMP</th><th>PROVIDER</th>"
                "<th>CATEGORY</th><th>SEV</th><th>DEVICE</th></tr>"
                + hist_rows + "</table>")

    body = (
        '<div class="sec"><div class="st">User Profile</div>'
        + kpi_row + "</div>"
        + '<div class="sec"><div class="st">AI Footprint</div>'
        + fp_tbl + "</div>"
        + '<div class="sec"><div class="st">Org Comparison</div>'
        + cmp_box + "</div>"
        + '<div class="sec"><div class="st">Recent Activity (Last 10)</div>'
        + hist_tbl + "</div>"
    )
    return _header.wrap_html(
        f"User Risk Report — {target_email}", body,
        company, d_from, d_to, admin_email, logo_b64
    )
