# =============================================================
# FILE: dashboard/ui/clickable_metric.py
# PROJECT: PatronAI — Mega-PR (drill-down everywhere)
# VERSION: 1.1.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Drop-in replacement for `st.metric()` that adds a thin
#          "↳ filter" button below the value. Clicking the button
#          opens a drill-down panel via drill_panel.set_drill().
# DEPENDS: streamlit, drill_panel
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Mega-PR.
#   v1.1.0  2026-05-11  Add optional sub_label — small grey volume
#                       indicator beneath the value (e.g. "1020 scan
#                       events" under a Devices=1 card). Lets the
#                       inventory tab show distinct-device counts as
#                       the headline number while preserving the raw
#                       row count as a secondary signal.
# =============================================================

from typing import Optional

import streamlit as st

from .drill_panel import set_drill


def clickable_metric(container, label: str, value,
                     panel_key: str, drill_field: str, drill_value,
                     drill_label: Optional[str] = None,
                     delta: Optional[str] = None,
                     help_text: Optional[str] = None,
                     sub_label: Optional[str] = None) -> None:
    """Render an st.metric tile + a drill button beneath it.

    Args:
      container:    Streamlit container/column to render into
      label:        Metric label ("Devices")
      value:        Metric value (int / str)
      panel_key:    Drill panel id (one per page region)
      drill_field:  Event dict key to filter on ("severity", "outcome", …)
      drill_value:  Value to match
      drill_label:  Chip text in the drill panel
      delta:        Same as st.metric delta
      help_text:    Same as st.metric help
      sub_label:    Optional small grey volume indicator under the value
                    — e.g. "1020 scan events". Lets the headline number
                    represent distinct entities while preserving the raw
                    row count as a secondary signal.
    """
    container.metric(label, value, delta=delta, help=help_text)
    if sub_label:
        container.markdown(
            f"<div style='font-family:JetBrains Mono;font-size:10px;"
            f"color:#8B949E;margin-top:-12px;margin-bottom:4px;'>"
            f"{sub_label}</div>",
            unsafe_allow_html=True,
        )
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
