# =============================================================
# FILE: dashboard/ui/manager_tab_logs.py
# VERSION: 2.1.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Log View tab — unified table for both network events
#          (packetbeat / zeek) and endpoint scan findings
#          (agent_endpoint_scan). Detects event type and renders
#          the right columns. Filters: type · severity · provider ·
#          department · search. CSV export. Icons throughout.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — network events only
#   v1.1.0  2026-04-19  Single-click CSV export
#   v2.0.0  2026-04-27  Unified network + endpoint rendering; icons;
#                       type filter; severity colors from theme.
#   v2.1.0  2026-04-28  Add ?view=user_detail hyperlink on USER column.
# =============================================================

from datetime import date

import pandas as pd
import streamlit as st

from .helpers        import sev_badge, geo_flag
from .filtered_table import search_box, apply_search_dicts
from .time_fmt       import fmt as fmt_time

_AGENT_SOURCES = {"agent_endpoint_scan", "patronai_scan_agent"}
_TYPE_LABELS   = {"ALL": "🔎 All types", "network": "🌐 Network",
                  "endpoint": "💻 Endpoint scan"}


def _is_endpoint(e: dict) -> bool:
    """True if this event came from an endpoint agent scan."""
    return (e.get("source", "") in _AGENT_SOURCES
            or e.get("outcome") == "ENDPOINT_FINDING")


def _row(e: dict) -> str:
    """Render one table row for either event type."""
    ts       = fmt_time(e.get("timestamp"))
    sev_html = sev_badge(e.get("severity", "LOW"))

    if _is_endpoint(e):
        who    = e.get("email") or e.get("owner") or "—"
        origin = e.get("device_id") or e.get("src_ip") or "—"
        what   = e.get("category", e.get("source", "—"))
        detail = (e.get("provider") or "—")[:38]
        dept   = e.get("department", "—")
        extra  = '<span style="font-size:10px;color:#6B7280">💻 scan</span>'
    else:
        who    = e.get("owner", "—")
        origin = e.get("src_ip", "—")
        what   = e.get("provider", "—")
        detail = (e.get("dst_domain") or "—")[:38]
        dept   = e.get("department", "—")
        kb     = round(e.get("bytes_out", 0) / 1024, 1)
        extra  = (f'<span style="font-family:JetBrains Mono;font-size:10px;'
                  f'color:#57606A">{kb} KB</span>')

    # Link owner email to user detail page when it looks like an email
    who_cell = (
        f"<a href='?view=user_detail&email={who}' "
        f"style='color:#0969DA;text-decoration:none'>{who}</a>"
        if "@" in who else who
    )
    return (f"<tr>"
            f"<td style='font-family:JetBrains Mono;font-size:10px;"
            f"color:#57606A'>{ts}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:11px;"
            f"color:#57606A'>{origin}</td>"
            f"<td>{who_cell}</td>"
            f"<td style='font-size:11px'>{what}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:10px'>{detail}</td>"
            f"<td style='font-size:11px'>{dept}</td>"
            f"<td>{sev_html}</td>"
            f"<td>{extra}</td>"
            f"</tr>")


def render_logs(events: list) -> None:
    """Unified log table — network + endpoint, with filters and search."""
    if not events:
        st.info("📭 No events found. The scanner may still be ingesting data.")
        return

    # ── Search ────────────────────────────────────────────────
    q = search_box("logs", placeholder="🔍  Search owner, provider, IP, domain …")

    # ── Filters ───────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])

    type_choice = c1.selectbox(
        "Type", list(_TYPE_LABELS.keys()),
        format_func=lambda k: _TYPE_LABELS[k],
        label_visibility="collapsed",
    )
    sev_opts  = sorted({e.get("severity", "") for e in events if e.get("severity")})
    prov_opts = sorted({e.get("provider", "")  for e in events if e.get("provider")})
    dept_opts = sorted({e.get("department", "") for e in events if e.get("department")})

    f_sev  = c2.selectbox("🔴 Severity",   ["ALL"] + sev_opts,  label_visibility="collapsed")
    f_prov = c3.selectbox("🏷 Provider",   ["ALL"] + prov_opts, label_visibility="collapsed")
    f_dept = c4.selectbox("🏢 Department", ["ALL"] + dept_opts, label_visibility="collapsed")

    # ── Apply filters ─────────────────────────────────────────
    filtered = events
    if type_choice == "network":
        filtered = [e for e in filtered if not _is_endpoint(e)]
    elif type_choice == "endpoint":
        filtered = [e for e in filtered if _is_endpoint(e)]
    if f_sev  != "ALL":
        filtered = [e for e in filtered if e.get("severity")   == f_sev]
    if f_prov != "ALL":
        filtered = [e for e in filtered if e.get("provider")   == f_prov]
    if f_dept != "ALL":
        filtered = [e for e in filtered if e.get("department") == f_dept]
    filtered = apply_search_dicts(filtered, q)[:300]

    # ── Empty state ───────────────────────────────────────────
    if not filtered:
        st.warning("⚠️ No events match the current filters. Try broadening your search.")
        return

    # ── Table ─────────────────────────────────────────────────
    rows_html = "".join(_row(e) for e in filtered)
    n_net  = sum(1 for e in filtered if not _is_endpoint(e))
    n_ep   = sum(1 for e in filtered if _is_endpoint(e))
    label  = (f"📋 LOG VIEW — {len(filtered)} events "
              f"({n_net} network · {n_ep} endpoint)")
    st.markdown(f'<div class="card-title">{label}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div style='overflow-x:auto;max-height:460px;overflow-y:auto'>"
        f"<table><thead><tr>"
        f"<th>TIMESTAMP</th><th>ORIGIN</th><th>USER</th>"
        f"<th>TYPE / PROVIDER</th><th>DETAIL</th><th>DEPT</th>"
        f"<th>SEVERITY</th><th>INFO</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    # ── Export ────────────────────────────────────────────────
    st.download_button(
        label="⬇ Export CSV",
        data=pd.DataFrame(filtered).to_csv(index=False),
        file_name=f"patronai_events_{date.today().isoformat()}.csv",
        mime="text/csv",
    )
