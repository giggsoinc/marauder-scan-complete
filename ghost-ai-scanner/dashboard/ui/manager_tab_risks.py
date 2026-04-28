# =============================================================
# FILE: dashboard/ui/manager_tab_risks.py
# VERSION: 2.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Risks tab — open alert list with row selection + real actions.
#          Mark Resolved writes to S3 findings store.
#          Escalate POSTs to Trinity via dispatcher.
#          Send Alert Email delivers SES summary.
#          In demo mode (no BUCKET) all write actions are blocked.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — extracted from steve_dashboard / manager_view
#   v2.0.0  2026-04-19  st.dataframe row selection + real Mark/Escalate/Email
# =============================================================

import os
import sys

import pandas as pd
import streamlit as st

from .helpers              import sev_badge
from .manager_tab_actions  import mark_resolved, escalate, send_alert_email
from .time_fmt             import fmt as fmt_time
from .filtered_table       import filtered_table

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}


def render_risks(events: list) -> None:
    """Selectable alert table + Mark Resolved / Escalate / Email actions."""
    alerts = sorted(      # .get() guards missing severity on endpoint events
        [e for e in events if e.get("severity") in _SEV_ORDER],
        key=lambda x: (_SEV_ORDER.get(x.get("severity", ""), 9),
                       x.get("timestamp", "")),
    )[:50]

    st.markdown(
        f'<div class="card-title">OPEN ALERTS — {len(alerts)} ITEMS</div>',
        unsafe_allow_html=True,
    )

    if not alerts:
        st.info("No open alerts.")
        return

    _COLS = ["timestamp", "severity", "provider", "owner",
             "department", "src_ip", "mac_address", "source", "outcome"]
    # Pre-format timestamps so the table renders DD-MMM-YY HH:MM:SS TZ
    # in the viewer's local time, not the raw ISO microsecond string.
    formatted = []
    for a in alerts:
        fa = dict(a)
        fa["timestamp"] = fmt_time(a.get("timestamp"))
        formatted.append(fa)
    _df_full = pd.DataFrame(formatted)
    df_alerts = _df_full[[c for c in _COLS if c in _df_full.columns]]

    # Phase 1B — wrap with filtered_table for the global search bar.
    _, selected_rows = filtered_table(
        df_alerts,
        key="risks",
        column_config={
            "severity":    st.column_config.TextColumn("SEV",  width="small"),
            "timestamp":   st.column_config.TextColumn("TIME", width="medium"),
            "mac_address": st.column_config.TextColumn("MAC",  width="medium"),
        },
        selection_mode="multi-row",
    )
    selected_events = [alerts[i] for i in selected_rows] if selected_rows else []

    if selected_rows:
        st.caption(f"{len(selected_rows)} event(s) selected.")
    else:
        st.caption("Click rows to select events, then use action buttons below.")

    st.markdown("<br>", unsafe_allow_html=True)
    bc1, bc2, bc3 = st.columns(3)

    with bc1:
        if st.button("✓ Mark Resolved", use_container_width=True):
            _action_resolve(selected_events)

    with bc2:
        if st.button("↑ Escalate to Trinity", use_container_width=True):
            _action_escalate(selected_events)

    with bc3:
        if st.button("✉ Send Alert Email", use_container_width=True):
            _action_email(selected_events)


def _demo_blocked() -> bool:
    """Return True and show info banner if running in demo mode."""
    if not _BUCKET:
        st.info("Actions are disabled in demo mode — "
                "connect a real S3 bucket to enable.")
        return True
    return False


def _action_resolve(selected_events: list) -> None:
    """Handle Mark Resolved button click."""
    if not selected_events:
        st.warning("Select one or more events first.")
        return
    if _demo_blocked():
        return
    try:
        from blob_index_store import BlobIndexStore
        store   = BlobIndexStore(_BUCKET, _REGION)
        resolved = mark_resolved(selected_events, store)
        st.success(f"✓ {resolved} event(s) marked resolved in S3.")
    except Exception as e:
        st.error(f"Failed to connect to tenant storage: {e}")


def _action_escalate(selected_events: list) -> None:
    """Handle Escalate button click."""
    if not selected_events:
        st.warning("Select one or more events first.")
        return
    if _demo_blocked():
        return
    sent = escalate(selected_events)
    if sent:
        st.success(f"✓ {sent} event(s) escalated to Trinity.")
    else:
        st.error("Escalation failed — check TRINITY_WEBHOOK_URL / ALERT_SNS_ARN.")


def _action_email(selected_events: list) -> None:
    """Handle Send Alert Email button click."""
    if not selected_events:
        st.warning("Select events first.")
        return
    if _demo_blocked():
        return
    recipients = os.environ.get("ALERT_RECIPIENTS", "")
    if not recipients:
        st.error("ALERT_RECIPIENTS not set in environment.")
        return
    ok = send_alert_email(selected_events, recipients)
    if ok:
        st.success(f"✓ Alert email sent to {recipients}.")
