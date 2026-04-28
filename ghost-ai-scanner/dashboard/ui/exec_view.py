# =============================================================
# FILE: dashboard/ui/exec_view.py
# VERSION: 2.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Exec view — AI governance KPI row + three-tab analysis.
#          Replaces Pam dashboard. Role: Security Executive / Platform Admin.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — renamed from pam_dashboard, de-branded
#   v2.0.0  2026-04-27  Mega-PR — KPIs are clickable, drill panel renders
#                       inline, all charts hand off to drill_panel.set_drill().
#   v2.1.0  2026-04-27  Fix KPI drill predicates — endpoint findings have
#                       outcome=ENDPOINT_FINDING (not ALERT); HIGH is the
#                       top severity for current scan data; alerts_fired
#                       computed live from events list.
# =============================================================

import streamlit as st
from .exec_tab_landscape import render_landscape
from .exec_tab_risk       import render_risk
from .exec_tab_exposure   import render_exposure
from .data                import load_yesterday_summary
from .clickable_metric    import clickable_metric, static_metric
from .drill_panel         import render_drill_panel

_PANEL = "exec_kpis"


def render(events: list, summary: dict) -> None:
    """Render the Exec view — KPIs, drill panel, then three tabs."""
    _kpis(events, summary)
    render_drill_panel(_PANEL, events, limit=100)
    st.markdown("<br>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["  AI LANDSCAPE  ", "  RISK HEATMAP  ", "  DATA EXPOSURE  "])
    with t1:
        render_landscape(events, summary)
    with t2:
        render_risk(events)
    with t3:
        render_exposure(events)


def _kpis(events: list, summary: dict) -> None:
    """Five KPI metrics with yesterday deltas. Each clickable except
    'AI Providers Detected'.
    NOTE: endpoint findings use outcome=ENDPOINT_FINDING (not ALERT),
    and max severity is HIGH (not CRITICAL). KPIs computed from the
    live events list so drills always match displayed counts."""
    ysum  = load_yesterday_summary()
    ysev  = ysum.get("by_severity", {})

    # Compute live from events — summary may be stale / network-event-biased
    findings   = [e for e in events if e.get("outcome") == "ENDPOINT_FINDING"]
    high_sev   = [e for e in events if e.get("severity") == "HIGH"]
    n_findings = len(findings)
    n_high     = len(high_sev)
    n_provs    = len(set(e.get("provider", "") for e in events if e.get("provider")))

    # Deltas vs yesterday summary (best-effort; 0 when yesterday unavailable)
    d_total = n_findings    - ysum.get("total_events",    0)
    d_high  = n_high        - ysev.get("HIGH",            0)
    d_provs = n_provs       - ysum.get("unique_providers", 0)
    d_fired = n_findings    - ysum.get("total_events",    0)   # same denominator

    c1, c2, c3, c4, c5 = st.columns(5)
    clickable_metric(c1, "AI Findings", n_findings,
                     panel_key=_PANEL,
                     drill_field="outcome", drill_value="ENDPOINT_FINDING",
                     drill_label="All endpoint findings",
                     delta=f"{d_total:+d} vs yesterday")
    clickable_metric(c2, "High Severity", n_high,
                     panel_key=_PANEL,
                     drill_field="severity", drill_value="HIGH",
                     drill_label="Severity = HIGH",
                     delta=f"{d_high:+d}")
    static_metric(c3, "AI Providers Detected", n_provs,
                  delta=f"{d_provs:+d} new" if d_provs else "no change")
    static_metric(c4, "Categories Found",
                  len(set(e.get("category", "") for e in findings
                          if e.get("category"))))
    clickable_metric(c5, "Alerts Fired", n_findings,
                     panel_key=_PANEL,
                     drill_field="outcome", drill_value="ENDPOINT_FINDING",
                     drill_label="Alerts fired — endpoint findings",
                     delta=f"{d_fired:+d} vs yesterday")
