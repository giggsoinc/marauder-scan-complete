# =============================================================
# FILE: dashboard/ui/manager_view.py
# VERSION: 1.3.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc
# PURPOSE: Manager view — infrastructure + pipeline tabs.
#          Role: SecOps Manager / Platform Admin.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — renamed from steve_dashboard, de-branded
#   v1.1.0  2026-04-26  Phase 1A — added 5th tab "AI INVENTORY".
#   v1.2.0  2026-04-28  Add 🤖 Ask AI chat widget.
#   v1.3.0  2026-04-29  Move chat widget to top of page.
# =============================================================

import streamlit as st

from .manager_tab_inventory     import render_inventory
from .manager_tab_risks         import render_risks
from .manager_tab_logs          import render_logs
from .manager_tab_pipeline      import render_pipeline
from .manager_tab_ai_inventory  import render_ai_inventory
from .chat                      import render_chat


def render(events: list, summary: dict, email: str = "") -> None:
    """Render the Manager view — AI chat header, five analysis tabs."""
    render_chat(events, email, "manager")
    st.markdown("---")
    t1, t2, t3, t4, t5 = st.tabs([
        "  INVENTORY  ", "  RISKS  ", "  LOG VIEW  ", "  PIPELINE  ",
        "  AI INVENTORY  ",
    ])
    with t1:
        render_inventory(events)
    with t2:
        render_risks(events)
    with t3:
        render_logs(events)
    with t4:
        render_pipeline(events, summary)
    with t5:
        render_ai_inventory(events)
