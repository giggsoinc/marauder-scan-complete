# =============================================================
# FILE: dashboard/ui/tabs/alerting.py
# VERSION: 1.1.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: Alerting settings tab — email channel, Trinity webhook,
#          LogAnalyzer webhook. No AWS service names exposed in UI.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v1.1.0  2026-04-20  grafana_url field — powers sidebar "Open dashboard" link
# =============================================================

import streamlit as st
from .. import audit as _audit


def render(store, email: str) -> None:
    """Alerting settings form with save and audit trail."""
    settings = store.settings.read()
    alerts   = settings.get("alerts", {})

    st.markdown("**Alert channels**")
    c1, c2 = st.columns(2)
    with c1:
        sns_arn = st.text_input(
            "Email channel ARN",
            value=alerts.get("sns_topic_arn", ""),
            help="Alert channel resource identifier (from your tenant setup).",
            label_visibility="visible",
        )
    with c2:
        trinity_url = st.text_input(
            "Trinity webhook",
            value=alerts.get("trinity_webhook_url", ""),
            help="Paste the webhook URL from your TrinityOps integration.",
        )

    loganalyzer_url = st.text_input(
        "LogAnalyzer webhook",
        value=alerts.get("loganalyzer_webhook_url", ""),
        help="Paste the LogAnalyzer ingest URL if enabled.",
    )

    st.markdown("---")
    st.markdown("**Dashboard link**")
    grafana_url = st.text_input(
        "Grafana URL",
        value=alerts.get("grafana_url", ""),
        help=(
            "Full URL to your Grafana instance, e.g. http://54.x.x.x/grafana  "
            "Powers the 'Open dashboard' link in the sidebar. "
            "Leave blank to use the GRAFANA_URL or PUBLIC_HOST env var."
        ),
        placeholder="http://<your-ec2-ip>/grafana",
    )

    st.markdown("**Thresholds**")
    alert_on_first = st.toggle(
        "Alert on first occurrence (no dedup)",
        value=alerts.get("alert_on_first", False),
        help="Send an alert immediately even if a similar event fired recently.",
    )

    if st.button("Save — Alerting", type="primary"):
        old = {
            "sns_topic_arn":           alerts.get("sns_topic_arn",           ""),
            "trinity_webhook_url":     alerts.get("trinity_webhook_url",     ""),
            "loganalyzer_webhook_url": alerts.get("loganalyzer_webhook_url", ""),
            "grafana_url":             alerts.get("grafana_url",             ""),
            "alert_on_first":          alerts.get("alert_on_first",          False),
        }
        settings.setdefault("alerts", {}).update({
            "sns_topic_arn":           sns_arn,
            "trinity_webhook_url":     trinity_url,
            "loganalyzer_webhook_url": loganalyzer_url,
            "grafana_url":             grafana_url,
            "alert_on_first":          alert_on_first,
        })
        new = {
            "sns_topic_arn":           sns_arn,
            "trinity_webhook_url":     trinity_url,
            "loganalyzer_webhook_url": loganalyzer_url,
            "grafana_url":             grafana_url,
            "alert_on_first":          alert_on_first,
        }
        try:
            ok = store.settings.write(settings, written_by=email)
            if ok:
                _audit.write_batch(email, {k: (old[k], new[k]) for k in old})
                # Refresh sidebar link immediately in this session
                import streamlit as _st
                _st.session_state["grafana_url"] = grafana_url
                st.success("Alerting settings saved.")
            else:
                st.error("Save failed — check tenant storage permissions.")
        except Exception as e:
            st.error(f"Save error: {e}")
