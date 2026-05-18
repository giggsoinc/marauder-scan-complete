# =============================================================
# FILE: dashboard/ui/support_view.py
# VERSION: 3.3.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Support team view — tab router.
#          RULES | CODE SIGNALS | COVERAGE | HEALTH | LOGS | RISKS |
#          PIPELINE | AGENT FLEET
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-20  Add Agent Fleet tab; remove demo mode references
#   v3.0.0  2026-04-27  Mega-PR — added LOGS / RISKS / PIPELINE tabs.
#   v3.1.0  2026-04-28  Add 🤖 Ask AI chat widget.
#   v3.2.0  2026-04-29  Move chat widget to top of page.
#   v3.3.0  2026-05-17  Signal filter (default ALL — support must see noise too).
#                       Signals/Risks/Logs receive filtered events; Rules/Coverage/
#                       Health/Pipeline/Fleet always receive full event list.
# =============================================================

import streamlit as st

from .support_tab_rules     import render_rules
from .support_tab_signals   import render_signals
from .support_tab_coverage  import render_coverage
from .support_tab_health    import render_health
from .support_tab_fleet     import render_fleet
from .manager_tab_logs      import render_logs
from .manager_tab_risks     import render_risks
from .manager_tab_pipeline  import render_pipeline

_SC_OPTIONS = ["📋 All signals", "🔴 Ghost only", "⚫ Noise only", "✅ No Issue"]
_SC_MAP     = {
    "🔴 Ghost only": "GHOST",
    "⚫ Noise only":  "NOISE",
    "✅ No Issue":    "NO_ISSUE",
}


def _signal_summary(events: list) -> None:
    """Compact inline KPI strip for support context."""
    ghost = sum(1 for e in events if e.get("signal_class") == "GHOST")
    noise = sum(1 for e in events if e.get("signal_class") == "NOISE")
    clean = sum(1 for e in events if e.get("signal_class") == "NO_ISSUE")
    uncl  = len(events) - ghost - noise - clean
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Ghost",        ghost)
    c2.metric("⚫ Noise",        noise)
    c3.metric("✅ No Issue",     clean)
    c4.metric("◻ Unclassified", uncl)


def render(events: list, summary: dict, store, email: str = "") -> None:
    """Render the Support view — signal summary, filter, eight analysis tabs."""
    st.markdown(
        '<div style="font-family:JetBrains Mono;font-size:11px;color:#57606A;'
        'letter-spacing:.08em;margin-bottom:8px;">SUPPORT TEAM VIEW</div>',
        unsafe_allow_html=True,
    )
    _signal_summary(events)

    choice = st.radio(
        "Signal filter",
        _SC_OPTIONS,
        horizontal=True, index=0, key="sup_sc_filter",
        help="Support default: ALL. Health/Pipeline/Fleet/Coverage/Rules tabs "
             "always show full dataset regardless of filter.",
    )
    sc_val   = _SC_MAP.get(choice)
    filtered = [e for e in events if e.get("signal_class") == sc_val] \
               if sc_val else events
    st.caption(f"{len(filtered)} of {len(events)} events · {choice}")
    st.divider()

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "  RULES  ", "  CODE SIGNALS  ", "  COVERAGE  ", "  HEALTH  ",
        "  LOGS  ", "  RISKS  ", "  PIPELINE  ", "  AGENT FLEET  ",
    ])
    with t1: render_rules(store)                    # no events
    with t2: render_signals(filtered)               # filtered — code signals by class
    with t3: render_coverage(store)                 # no events — structural
    with t4: render_health(events, summary)         # full — fleet health is all events
    with t5: render_logs(filtered)                  # filtered — follow signal filter
    with t6: render_risks(filtered)                 # filtered — risk queue
    with t7: render_pipeline(events, summary)       # full — pipeline is infra
    with t8: render_fleet(email)                    # no events — agent fleet
