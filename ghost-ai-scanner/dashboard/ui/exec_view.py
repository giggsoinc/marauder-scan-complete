# =============================================================
# FILE: dashboard/ui/exec_view.py
# VERSION: 2.4.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Exec view — AI governance KPI row + three-tab analysis.
#          Replaces Pam dashboard. Role: Security Executive / Platform Admin.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — renamed from pam_dashboard, de-branded
#   v2.0.0  2026-04-27  Mega-PR — KPIs are clickable, drill panel renders
#                       inline, all charts hand off to drill_panel.set_drill().
#   v2.1.0  2026-04-27  Fix KPI drill predicates — outcome=ENDPOINT_FINDING.
#   v2.2.0  2026-04-28  Add 🤖 Ask AI chat widget.
#   v2.3.0  2026-04-29  Move chat widget to top of page.
#   v2.4.0  2026-05-17  Ghost KPI card + signal filter toggle. Risk Heatmap
#                       and Data Exposure tabs receive filtered events.
#                       AI Landscape receives full events (exec needs full picture).
# =============================================================

import streamlit as st
from .exec_tab_landscape import render_landscape
from .exec_tab_risk       import render_risk
from .exec_tab_exposure   import render_exposure
from .data                import load_yesterday_summary
from .clickable_metric    import clickable_metric, static_metric
from .drill_panel         import render_drill_panel

_PANEL = "exec_kpis"


def render(events: list, summary: dict, email: str = "") -> None:
    """Render the Exec view — KPIs, ghost filter, drill panel, three tabs."""
    _kpis(events, summary)
    render_drill_panel(_PANEL, events, limit=100)
    st.markdown("<br>", unsafe_allow_html=True)

    ghost_only = st.toggle(
        "🔴 Ghost signals only",
        value=True, key="exec_ghost_toggle",
        help="ON = show only confirmed unauthorized AI (Ghost). "
             "OFF = show all findings including noise.",
    )
    filtered = [e for e in events if e.get("signal_class") == "GHOST"] \
               if ghost_only else events
    st.caption(f"{len(filtered)} of {len(events)} events · "
               f"{'Ghost signals only' if ghost_only else 'All signals'}")

    t1, t2, t3 = st.tabs(["  AI LANDSCAPE  ", "  RISK HEATMAP  ", "  DATA EXPOSURE  "])
    with t1:
        render_landscape(events, summary)   # full — exec needs complete AI landscape
    with t2:
        render_risk(filtered)               # filtered — risk heatmap shows real threats
    with t3:
        render_exposure(filtered)           # filtered — exposure = ghost activity only


def _kpis(events: list, summary: dict) -> None:
    """Six KPI metrics — Ghost Signals added as first card, then legacy metrics.
    NOTE: endpoint findings use outcome=ENDPOINT_FINDING (not ALERT),
    max severity is HIGH (not CRITICAL). KPIs computed from live events
    so drills always match displayed counts."""
    ysum  = load_yesterday_summary()
    ysev  = ysum.get("by_severity", {})

    ghost_events = [e for e in events if e.get("signal_class") == "GHOST"]
    findings     = [e for e in events if e.get("outcome") == "ENDPOINT_FINDING"]
    high_sev     = [e for e in events if e.get("severity") == "HIGH"]
    n_ghost      = len(ghost_events)
    n_findings   = len(findings)
    n_high       = len(high_sev)
    n_provs      = len(set(e.get("provider", "") for e in events if e.get("provider")))

    d_total = n_findings - ysum.get("total_events",    0)
    d_high  = n_high     - ysev.get("HIGH",            0)
    d_provs = n_provs    - ysum.get("unique_providers", 0)
    d_ghost = n_ghost    - ysum.get("ghost_signals",   0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    clickable_metric(c1, "🔴 Ghost Signals", n_ghost,
                     panel_key=_PANEL,
                     drill_field="signal_class", drill_value="GHOST",
                     drill_label="Ghost signals — confirmed unauthorized AI",
                     delta=f"{d_ghost:+d} vs yesterday")
    clickable_metric(c2, "AI Findings", n_findings,
                     panel_key=_PANEL,
                     drill_field="outcome", drill_value="ENDPOINT_FINDING",
                     drill_label="All endpoint findings",
                     delta=f"{d_total:+d} vs yesterday")
    clickable_metric(c3, "High Severity", n_high,
                     panel_key=_PANEL,
                     drill_field="severity", drill_value="HIGH",
                     drill_label="Severity = HIGH",
                     delta=f"{d_high:+d}")
    static_metric(c4, "AI Providers", n_provs,
                  delta=f"{d_provs:+d} new" if d_provs else "no change")
    static_metric(c5, "Categories",
                  len(set(e.get("category", "") for e in findings
                          if e.get("category"))))
    clickable_metric(c6, "Alerts Fired", n_findings,
                     panel_key=_PANEL,
                     drill_field="outcome", drill_value="ENDPOINT_FINDING",
                     drill_label="Alerts fired — endpoint findings",
                     delta=f"{d_total:+d} vs yesterday")
