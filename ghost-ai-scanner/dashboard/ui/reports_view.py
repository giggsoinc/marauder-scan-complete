# =============================================================
# FILE: dashboard/ui/reports_view.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Reports page — 7 downloadable report cards.
#          Each card: date-range pickers → 👁 Preview (HTML inline)
#          → ⬇ Download PDF (weasyprint). R3 adds user picker.
# DEPENDS: streamlit, reports package, data.py
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import os
from datetime import date, timedelta

import streamlit as st

from .reports._logo  import fetch_logo_b64
from .reports._pdf   import html_to_pdf
from .reports        import r1_exec, r2_inventory, r3_user
from .reports        import r4_incidents, r5_fleet, r6_compliance, r7_shadow
from .manager_tab_ai_inventory_data import owners_in, phase_1a_only

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_CO     = os.environ.get("COMPANY_NAME", "PatronAI")

_REPORTS = [
    ("R1", "📋 Executive Risk Summary",
     "High-level AI risk overview for leadership.", r1_exec, False),
    ("R2", "🗂 AI Asset Inventory",
     "All detected AI assets deduped to latest observation.", r2_inventory, False),
    ("R3", "👤 User Risk Report",
     "Per-user AI footprint, risk profile, and org comparison.", r3_user, True),
    ("R4", "🚨 Incident / Findings",
     "All ENDPOINT_FINDING events for the period.", r4_incidents, False),
    ("R5", "💻 Fleet Health & Coverage",
     "Agent heartbeats, coverage gaps, pipeline state.", r5_fleet, False),
    ("R6", "🔒 Compliance Audit Trail",
     "Immutable findings export with SHA-256 integrity hash.", r6_compliance, False),
    ("R7", "🤖 Shadow AI Census",
     "All AI providers detected across the organisation.", r7_shadow, False),
]


def _default_range() -> tuple:
    """Return (30-days-ago ISO str, today ISO str)."""
    today = date.today()
    return (today - timedelta(days=30)).isoformat(), today.isoformat()


def _card(rid: str, title: str, desc: str, builder,
          needs_user: bool, events: list, email: str) -> None:
    """Render one report card with date pickers, preview, and PDF download."""
    st.markdown(
        f"<div style='background:#F6F8FA;border:1px solid #D0D7DE;"
        f"border-radius:8px;padding:16px;margin-bottom:16px'>"
        f"<div style='font-size:14px;font-weight:700'>{title}</div>"
        f"<div style='font-size:11px;color:#57606A;margin-top:2px'>{desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    d_from_def, d_to_def = _default_range()
    cols = st.columns([1, 1, 2, 1]) if needs_user else st.columns([1, 1, 1])
    d_from = str(cols[0].date_input("From", value=date.fromisoformat(d_from_def),
                                    key=f"{rid}_from"))
    d_to   = str(cols[1].date_input("To",   value=date.fromisoformat(d_to_def),
                                    key=f"{rid}_to"))
    target = ""
    if needs_user:
        owners = owners_in(phase_1a_only(events))
        target = cols[2].selectbox("User", [""] + owners, key=f"{rid}_user",
                                   format_func=lambda x: x or "(select user)")
    logo_b64 = fetch_logo_b64(_BUCKET, _REGION)

    btn_col, dl_col = st.columns([1, 4])
    if btn_col.button("👁 Preview", key=f"{rid}_prev"):
        try:
            kwargs = dict(events=events, d_from=d_from, d_to=d_to,
                          admin_email=email, company=_CO, logo_b64=logo_b64)
            if needs_user:
                kwargs["target_email"] = target
            st.session_state[f"{rid}_html"] = builder.build_html(**kwargs)
        except Exception as exc:
            st.error(f"Report build failed: {exc}")

    html_key = f"{rid}_html"
    if html_key in st.session_state:
        html_str = st.session_state[html_key]
        st.components.v1.html(html_str, height=820, scrolling=True)
        dc1, dc2 = st.columns([1, 8])
        with dc1:
            try:
                pdf_bytes = html_to_pdf(html_str)
                fname = f"patronai_{rid.lower()}_{date.today()}.pdf"
                st.download_button("⬇ PDF", data=pdf_bytes,
                                   file_name=fname, mime="application/pdf",
                                   key=f"{rid}_dl")
            except RuntimeError as exc:
                st.warning(str(exc))
        with dc2:
            if st.button("✕ Close", key=f"{rid}_close"):
                del st.session_state[html_key]
                st.rerun()


def render_reports(events: list, email: str) -> None:
    """Top-level Reports page — called from ghost_dashboard.py."""
    st.markdown("### 📄 Reports")
    st.caption(
        "Select a report, pick a date range, click **👁 Preview** "
        "to review the HTML design, then **⬇ PDF** to download."
    )
    st.divider()
    for rid, title, desc, builder, needs_user in _REPORTS:
        _card(rid, title, desc, builder, needs_user, events, email)
