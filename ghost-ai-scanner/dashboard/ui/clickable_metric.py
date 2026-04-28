# =============================================================
# FILE: dashboard/ui/clickable_metric.py
# PROJECT: PatronAI — Mega-PR (drill-down everywhere)
# VERSION: 1.0.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Drop-in replacement for `st.metric()` that adds a thin
#          "↳ filter" button below the value. Clicking the button
#          opens a drill-down panel via drill_panel.set_drill().
#          Visually preserves Streamlit's native metric tile look so
#          the dashboard rhythm stays unchanged.
# DEPENDS: streamlit, drill_panel
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Mega-PR.
# =============================================================

from typing import Optional

import streamlit as st

from .drill_panel import set_drill


def clickable_metric(container, label: str, value,
                     panel_key: str, drill_field: str, drill_value,
                     drill_label: Optional[str] = None,
                     delta: Optional[str] = None,
                     help_text: Optional[str] = None) -> None:
    """Render an st.metric tile + a drill button beneath it.

    Args:
      container:    Streamlit container/column to render into
      label:        Metric label ("Unauthorized events")
      value:        Metric value (int / str)
      panel_key:    Drill panel id (one per page region — KPIs of one tab
                    typically share a panel_key so clicking another KPI
                    replaces the previous drill instead of stacking)
      drill_field:  Event dict key to filter on ("severity", "outcome", …)
      drill_value:  Value to match (e.g. "CRITICAL", "BLOCK")
      drill_label:  Chip text in the drill panel (defaults to f"{label}: {drill_value}")
      delta:        Same as st.metric delta
      help_text:    Same as st.metric help

    On click, sets the drill state — the calling page is expected to
    invoke render_drill_panel(panel_key, events) somewhere below the
    KPI row to surface the filtered table.
    """
    container.metric(label, value, delta=delta, help=help_text)
    btn_key = f"clk_{panel_key}_{label.replace(' ', '_').lower()}"
    if container.button(f"↳ filter", key=btn_key):
        set_drill(
            panel_key=panel_key,
            label=drill_label or f"{label}: {drill_value}",
            field=drill_field,
            value=drill_value,
        )
        st.rerun()


def static_metric(container, label: str, value,
                  delta: Optional[str] = None,
                  help_text: Optional[str] = None) -> None:
    """Plain non-clickable metric — convenience pass-through so a
    KPI row can mix drillable + static cells without two import paths."""
    container.metric(label, value, delta=delta, help=help_text)
