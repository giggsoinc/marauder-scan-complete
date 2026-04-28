# =============================================================
# FILE: dashboard/ui/support_tab_signals.py
# VERSION: 1.1.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc
# PURPOSE: Support CODE SIGNALS tab — git hook and filesystem watcher
#          events from agent fleet. Shows pending triage queue with
#          repo, branch, snippet preview, and status badges.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v1.1.0  2026-04-28  Fix "Pending triage" drill: DOMAIN_ALERT →
#                       PENDING_TRIAGE (actual outcome for code signals).
#                       Fix today filter: use timestamp not missing date.
#                       Add ?view=user_detail owner links in signal table.
# =============================================================

from datetime import date

import streamlit as st

from .filtered_table   import search_box, apply_search_dicts
from .time_fmt         import fmt as fmt_time
from .clickable_metric import clickable_metric, static_metric
from .drill_panel      import render_drill_panel

_PANEL = "sup_signals"

_SIGNAL_SOURCES = {
    "agent_git_hook", "agent_fs_watcher",
    "patronai_git_hook", "patronai_git_hook_ps",
    "marauder_scan_git_hook",
}

_STATUS_BADGE = {
    "RESOLVED":     '<span class="badge badge-clean">RESOLVED</span>',
    "DOMAIN_ALERT": '<span class="badge badge-medium">PENDING TRIAGE</span>',
}
_DEFAULT_STATUS = '<span class="badge badge-medium">PENDING TRIAGE</span>'


def _status_html(outcome: str) -> str:
    """Pre-rendered badge HTML, factored out so the f-string row builder
    doesn't need a backslash-escape (which is illegal pre-Py3.12)."""
    return _STATUS_BADGE.get(outcome, _DEFAULT_STATUS)


def render_signals(events: list) -> None:
    """Code signals tab — agent-sourced git diff events."""
    today = date.today().isoformat()
    signals = [e for e in events if e.get("source", "") in _SIGNAL_SOURCES]
    # FLAT_SCHEMA has no 'date' field — use timestamp for today filter
    today_signals = [
        e for e in signals
        if (e.get("date") or e.get("timestamp", "")).startswith(today)
    ]
    pending = [e for e in signals if e.get("outcome", "") == "PENDING_TRIAGE"]

    # Phase 1B — global search across the signal stream.
    q = search_box("signals", placeholder="search repo / file / snippet …")
    if q:
        signals = apply_search_dicts(signals, q)

    c1, c2, c3 = st.columns(3)
    static_metric(c1,    "Total code signals", len(signals))
    static_metric(c2,    "Signals today",      len(today_signals))
    clickable_metric(c3, "Pending triage",     len(pending),
                     panel_key=_PANEL, drill_field="outcome",
                     drill_value="PENDING_TRIAGE",
                     drill_label="Pending (outcome=PENDING_TRIAGE)")
    render_drill_panel(_PANEL, signals, limit=100)

    if not signals:
        st.info("No code signals detected. Agent git hooks forward AI-pattern "
                "diffs here when they fire on developer commits.")
        return

    def _sig_row(e: dict) -> str:
        owner = e.get("email") or e.get("owner") or ""
        device = e.get("src_ip") or e.get("device_id") or "—"
        owner_cell = (
            f"<a href='?view=user_detail&email={owner}' "
            f"style='color:#0969DA;text-decoration:none'>{owner}</a>"
            if owner else "—"
        )
        return (
            f"<tr>"
            f"<td style='font-family:JetBrains Mono;font-size:10px;color:#57606A'>"
            f"{fmt_time(e.get('timestamp'))}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:10px'>{device}</td>"
            f"<td>{owner_cell}</td>"
            f"<td style='color:#0969DA;font-size:11px'>{e.get('process_name','—')}</td>"
            f"<td style='font-size:10px;color:#57606A'>{e.get('notes','—')[:40]}</td>"
            f"<td>{_status_html(e.get('outcome', ''))}</td>"
            f"</tr>"
        )

    rows = "".join(_sig_row(e) for e in signals[:30])
    st.markdown('<div class="card-title">CODE SIGNAL QUEUE</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='overflow-x:auto;max-height:380px;overflow-y:auto'>"
        f"<table><thead><tr>"
        f"<th>TIME</th><th>DEVICE</th><th>OWNER</th><th>REPO</th>"
        f"<th>SNIPPET</th><th>STATUS</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    st.caption("Resolve via Manager view → Risks tab → Mark Resolved.")
