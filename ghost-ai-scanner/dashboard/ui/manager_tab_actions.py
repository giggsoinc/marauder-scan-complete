# =============================================================
# FILE: dashboard/ui/manager_tab_actions.py
# VERSION: 2.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc
# PURPOSE: Action helpers for the Manager Risks tab.
#          mark_resolved — writes RESOLVED outcome back to S3 findings store.
#          escalate      — POSTs events to Trinity via dispatcher.
#          send_alert_email — thin shim: delegates to notify.email.send_alert.
#          All functions are pure — no Streamlit calls inside.
# DEPENDS: requests, alerter.dispatcher, notify.email
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — split from manager_tab_risks.py
#   v2.0.0  2026-05-02  send_alert_email body collapsed to a one-line
#                       call into notify.email.send_alert. The duplicated
#                       boto3 SES path here used PATRONAI_FROM_EMAIL +
#                       skipped recipient verification, both inconsistent
#                       with the welcome / OTP paths. notify.email is
#                       now the single SES call site for the codebase.
# =============================================================

import logging
import os
import sys
from datetime import datetime, timezone

log = logging.getLogger("patronai.ui.actions")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def mark_resolved(events: list, store) -> int:
    """
    Write each event back with outcome=RESOLVED.
    Uses findings_store.write() — append-only JSONL; scanner dedupes by event_id.
    Returns count of events successfully written.
    """
    count = 0
    for evt in events:
        try:
            resolved = dict(evt)
            resolved["outcome"]     = "RESOLVED"
            resolved["resolved_at"] = datetime.now(timezone.utc).isoformat()
            store.findings.write(resolved)
            count += 1
        except Exception as e:
            log.error("mark_resolved failed for %s: %s", evt.get("event_id", "?"), e)
    return count


def escalate(events: list) -> int:
    """
    POST each event to Trinity webhook + SNS via dispatcher.
    Returns count of events successfully dispatched.
    """
    try:
        from alerter.dispatcher import dispatch
    except ImportError as e:
        log.error("Cannot import dispatcher: %s", e)
        return 0

    webhook = os.environ.get("TRINITY_WEBHOOK_URL", "")
    sns_arn = os.environ.get("ALERT_SNS_ARN", "")
    count   = 0

    for evt in events:
        try:
            subject = (f"PatronAI Escalation — [{evt.get('severity','?')}] "
                       f"{evt.get('provider','?')} · {evt.get('owner','unknown')}")
            result  = dispatch(
                payload     = evt,
                subject     = subject,
                sns_arn     = sns_arn,
                webhook_url = webhook,
                region      = _AWS_REGION,
            )
            if "warning" not in result:
                count += 1
        except Exception as e:
            log.error("escalate failed for %s: %s", evt.get("event_id", "?"), e)

    return count


def send_alert_email(events: list, recipients: str) -> bool:
    """Send a bulleted summary of N selected events to a comma-separated
    recipient list. Thin shim — actual SES work lives in notify.email."""
    from notify.email import send_alert
    return send_alert(recipients=recipients, events=events)
