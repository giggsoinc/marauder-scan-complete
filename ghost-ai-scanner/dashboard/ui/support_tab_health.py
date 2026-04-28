# =============================================================
# FILE: dashboard/ui/support_tab_health.py
# VERSION: 1.2.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Support HEALTH tab — agent fleet heartbeats, code signal
#          counts, git diff counts, dedup suppression rate, and
#          scanner pipeline state. Gives Support a full fleet view.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v1.1.0  2026-04-27  Pipeline metrics now drill-through clickable
#                       (Files processed / Total events → inline table).
#   v1.2.0  2026-04-28  Fix "Alerts fired" drill: ALERT → ENDPOINT_FINDING.
#                       Fix empty drills on Files processed / Total events.
#                       Fix today filter: use timestamp not missing date field.
# =============================================================

from datetime import date

import streamlit as st

from .time_fmt          import fmt as fmt_time
from .clickable_metric  import clickable_metric, static_metric
from .drill_panel       import render_drill_panel

_PANEL          = "sup_health"
_PIPELINE_PANEL = "sup_pipeline"

_HEARTBEAT_SOURCES = {"agent_heartbeat"}
_GIT_SOURCES       = {"agent_git_hook", "patronai_git_hook",
                      "patronai_git_hook_ps", "marauder_scan_git_hook"}
_CODE_SOURCES      = {"agent_fs_watcher", "agent_git_hook",
                      "patronai_git_hook", "patronai_git_hook_ps"}
_SUPPRESS_OUTCOME  = "SUPPRESS"


def render_health(events: list, summary: dict) -> None:
    """Health tab — fleet metrics + pipeline state."""
    from .data import load_pipeline_state
    pipeline = load_pipeline_state()
    today    = date.today().isoformat()

    # FLAT_SCHEMA has no 'date' field — use timestamp for today filter
    today_events = [
        e for e in events
        if (e.get("date") or e.get("timestamp", "")).startswith(today)
    ]

    heartbeats  = len([e for e in today_events
                       if e.get("source", "") in _HEARTBEAT_SOURCES])
    git_diffs   = len([e for e in today_events
                       if e.get("source", "") in _GIT_SOURCES])
    code_sigs   = len([e for e in today_events
                       if e.get("source", "") in _CODE_SOURCES])
    suppressed  = len([e for e in events if e.get("outcome") == _SUPPRESS_OUTCOME])
    total       = len(events)
    dedup_rate  = f"{suppressed/total*100:.1f}%" if total else "0%"

    st.markdown('<div class="card-title">AGENT FLEET — TODAY</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    clickable_metric(c1, "Heartbeats today", heartbeats,
                     panel_key=_PANEL, drill_field="source",
                     drill_value="agent_heartbeat",
                     drill_label="source = agent_heartbeat")
    clickable_metric(c2, "Git diff signals", git_diffs,
                     panel_key=_PANEL, drill_field="source",
                     drill_value="agent_git_hook",
                     drill_label="source = agent_git_hook")
    clickable_metric(c3, "Code signals", code_sigs,
                     panel_key=_PANEL, drill_field="source",
                     drill_value="agent_fs_watcher",
                     drill_label="source = agent_fs_watcher")
    clickable_metric(c4, "Dedup suppression rate", dedup_rate,
                     panel_key=_PANEL, drill_field="outcome",
                     drill_value="SUPPRESS",
                     drill_label="outcome = SUPPRESS")
    render_drill_panel(_PANEL, events, limit=100)

    st.markdown('<div class="card-title">SCANNER PIPELINE</div>',
                unsafe_allow_html=True)
    p1, p2, p3 = st.columns(3)
    clickable_metric(p1, "Files processed", pipeline.get("files_processed", 0),
                     panel_key=_PIPELINE_PANEL, drill_field="source",
                     drill_value="agent_endpoint_scan",
                     drill_label="Source = agent_endpoint_scan")
    clickable_metric(p2, "Total events ingested", pipeline.get("total_events", 0),
                     panel_key=_PIPELINE_PANEL, drill_field="outcome",
                     drill_value="ENDPOINT_FINDING",
                     drill_label="All endpoint findings")
    last = pipeline.get("last_processed_at") or ""
    p3.metric("Last processed", fmt_time(last) if last else "—")
    render_drill_panel(_PIPELINE_PANEL, events, limit=100)

    last_key = pipeline.get("last_key", "—") or "—"
    st.markdown('<div class="card-title">LAST PROCESSED KEY</div>',
                unsafe_allow_html=True)
    st.code(last_key, language=None)

    st.markdown('<div class="card-title">SUMMARY SNAPSHOT</div>',
                unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    static_metric(s1,    "Total events",     summary.get("total_events", 0))
    # alerts_fired in summary counts DOMAIN_ALERT/PORT_ALERT — not endpoint data.
    # Compute from live events for accuracy; drill on the actual outcome value.
    live_alerts = len([e for e in events if e.get("outcome") == "ENDPOINT_FINDING"])
    clickable_metric(s2, "Alerts fired",     live_alerts,
                     panel_key=_PANEL, drill_field="outcome",
                     drill_value="ENDPOINT_FINDING",
                     drill_label="Endpoint findings")
    static_metric(s3, "Unique providers", summary.get("unique_providers", 0))
    static_metric(s4, "Unique sources",   summary.get("unique_sources", 0))
