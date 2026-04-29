# =============================================================
# FILE: dashboard/ui/support_view.py
# VERSION: 3.1.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Support team view — tab router.
#          RULES | CODE SIGNALS | COVERAGE | HEALTH | LOGS | RISKS |
#          PIPELINE | AGENT FLEET
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-20  Add Agent Fleet tab; remove demo mode references
#   v3.0.0  2026-04-27  Mega-PR — added LOGS / RISKS / PIPELINE tabs.
#   v3.1.0  2026-04-28  Add 🤖 Ask AI chat widget.
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
from .chat                  import render_chat


def render(events: list, summary: dict, store,
           email: str = "") -> None:
    """Render the Support view with eight analysis tabs + AI chat."""
    st.markdown(
        '<div style="font-family:JetBrains Mono;font-size:11px;color:#57606A;'
        'letter-spacing:.08em;margin-bottom:8px;">SUPPORT TEAM VIEW</div>',
        unsafe_allow_html=True,
    )
    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "  RULES  ", "  CODE SIGNALS  ", "  COVERAGE  ", "  HEALTH  ",
        "  LOGS  ", "  RISKS  ", "  PIPELINE  ", "  AGENT FLEET  ",
    ])
    with t1: render_rules(store)
    with t2: render_signals(events)
    with t3: render_coverage(store)
    with t4: render_health(events, summary)
    with t5: render_logs(events)
    with t6: render_risks(events)
    with t7: render_pipeline(events, summary)
    with t8: render_fleet(email)
    st.markdown("---")
    render_chat(events, email, "support")
