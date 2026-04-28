# =============================================================
# FILE: dashboard/ui/manager_tab_actions.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Action helpers for the Manager Risks tab.
#          mark_resolved — writes RESOLVED outcome back to S3 findings store.
#          escalate      — POSTs events to Trinity via dispatcher.
#          send_alert_email — sends SES summary to ALERT_RECIPIENTS.
#          All functions are pure — no Streamlit calls inside.
# DEPENDS: boto3, requests, alerter.dispatcher, blob_index_store
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — split from manager_tab_risks.py
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
    """
    Send SES email summarising selected events to comma-separated recipients.
    Returns True on success.
    """
    import boto3

    from .time_fmt import fmt as _fmt_time
    body_lines = [f"PatronAI Alert — {len(events)} event(s) require attention\n"]
    for e in events[:10]:
        body_lines.append(
            f"  [{e.get('severity','?')}] {e.get('provider','?')} | "
            f"{e.get('owner','unknown')} | {_fmt_time(e.get('timestamp'))}"
        )
    if len(events) > 10:
        body_lines.append(f"  … and {len(events) - 10} more.")
    body = "\n".join(body_lines)

    try:
        ses = boto3.client("ses", region_name=_AWS_REGION)
        ses.send_email(
            Source=os.environ.get("PATRONAI_FROM_EMAIL", "noreply@patronai.ai"),
            Destination={"ToAddresses": [r.strip() for r in recipients.split(",")]},
            Message={
                "Subject": {"Data": f"PatronAI Alert — {len(events)} event(s)"},
                "Body":    {"Text": {"Data": body}},
            },
        )
        log.info("Alert email sent to %s", recipients)
        return True
    except Exception as e:
        log.error("SES send_alert_email failed: %s", e)
        return False
