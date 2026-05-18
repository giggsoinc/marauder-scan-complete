# =============================================================
# FILE: dashboard/ui/manager_view.py
# VERSION: 1.4.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc
# PURPOSE: Manager view — infrastructure + pipeline tabs.
#          Role: SecOps Manager / Platform Admin.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — renamed from steve_dashboard, de-branded
#   v1.1.0  2026-04-26  Phase 1A — added 5th tab "AI INVENTORY".
#   v1.2.0  2026-04-28  Add 🤖 Ask AI chat widget.
#   v1.3.0  2026-04-29  Move chat widget to top of page.
#   v1.4.0  2026-05-17  Signal filter — GHOST/NOISE/ALL selector with KPI row.
#                       Risks/Logs/AI Inventory receive filtered events;
#                       Inventory and Pipeline always receive full event list.
# =============================================================

import streamlit as st

from .manager_tab_inventory     import render_inventory
from .manager_tab_risks         import render_risks
from .manager_tab_logs          import render_logs
from .manager_tab_pipeline      import render_pipeline
from .manager_tab_ai_inventory  import render_ai_inventory


def _signal_kpis(events: list) -> None:
    """Three-column KPI row: Ghost count, Noise count, No-Issue count."""
    ghost  = sum(1 for e in events if e.get("signal_class") == "GHOST")
    noise  = sum(1 for e in events if e.get("signal_class") == "NOISE")
    clean  = sum(1 for e in events if e.get("signal_class") == "NO_ISSUE")
    unclassified = len(events) - ghost - noise - clean
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Ghost Signals",  ghost,
              help="Systematic unauthorized AI — act on these")
    c2.metric("⚫ Noise",          noise,
              help="Automated / one-off — not shadow AI")
    c3.metric("✅ No Issue",       clean,
              help="Authorized activity (suppressed)")
    c4.metric("◻ Unclassified",   unclassified,
              help="Legacy rows before classifier ran — will clear next compact cycle")


def _filter_events(events: list, choice: str) -> list:
    """Return events matching the filter choice."""
    if choice == "🔴 Ghost only":
        return [e for e in events if e.get("signal_class") == "GHOST"]
    if choice == "⚫ Noise only":
        return [e for e in events if e.get("signal_class") == "NOISE"]
    return events  # "📋 All signals"


def render(events: list, summary: dict, email: str = "") -> None:
    """Render the Manager view — signal KPIs, filter, five analysis tabs."""
    _signal_kpis(events)
    st.markdown("<br>", unsafe_allow_html=True)

    choice = st.radio(
        "Signal filter",
        ["🔴 Ghost only", "📋 All signals", "⚫ Noise only"],
        horizontal=True, index=0, key="mgr_sc_filter",
        help="Ghost = systematic unauthorized AI. Noise = automated/one-off. "
             "Pipeline and Inventory tabs always show full dataset.",
    )
    filtered = _filter_events(events, choice)
    st.caption(f"Showing {len(filtered)} of {len(events)} events — {choice}")
    st.divider()

    t1, t2, t3, t4, t5 = st.tabs([
        "  INVENTORY  ", "  RISKS  ", "  LOG VIEW  ", "  PIPELINE  ",
        "  AI INVENTORY  ",
    ])
    with t1:
        render_inventory(events)          # full — inventory is structural
    with t2:
        render_risks(filtered)            # filtered — this is the risk queue
    with t3:
        render_logs(filtered)             # filtered — log view follows risk filter
    with t4:
        render_pipeline(events, summary)  # full — pipeline health is infra, not signal
    with t5:
        render_ai_inventory(filtered)     # filtered — show what AI tools are in use
