# =============================================================
# FILE: dashboard/ui/manager_view.py
# VERSION: 1.1.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc
# PURPOSE: Manager view — infrastructure + pipeline tabs.
#          Role: SecOps Manager / Platform Admin.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — renamed from steve_dashboard, de-branded
#   v1.1.0  2026-04-26  Phase 1A — added 5th tab "AI INVENTORY" surfacing
#                       MCP servers / agent workflows / scheduled / tools /
#                       vector DBs. Owner cells in that tab link to the
#                       Asset Map view (handled by ghost_dashboard.main()).
# =============================================================

import streamlit as st

from .manager_tab_inventory     import render_inventory
from .manager_tab_risks         import render_risks
from .manager_tab_logs          import render_logs
from .manager_tab_pipeline      import render_pipeline
from .manager_tab_ai_inventory  import render_ai_inventory


def render(events: list, summary: dict) -> None:
    """Render the Manager view — five analysis tabs."""
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
