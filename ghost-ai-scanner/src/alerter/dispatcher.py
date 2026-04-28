# =============================================================
# FILE: src/alerter/dispatcher.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Fire alerts to SNS and Trinity webhook.
#          Both channels run independently — one failure does not
#          block the other. Returns dict of dispatch results.
# DEPENDS: boto3, requests
# =============================================================

import json
import logging
import boto3
import requests

log = logging.getLogger("marauder-scan.alerter.dispatcher")

REQUEST_TIMEOUT = 5  # seconds


def dispatch(
    payload: dict,
    subject: str,
    sns_arn: str     = "",
    webhook_url: str = "",
    region: str      = "us-east-1",
) -> dict:
    """
    Send alert payload to all configured channels.
    SNS and webhook run independently.
    Returns results dict for audit logging.
    """
    results = {}

    # Fire SNS
    if sns_arn:
        results["sns"] = _fire_sns(payload, subject, sns_arn, region)

    # Fire Trinity webhook
    if webhook_url:
        results["trinity"] = _fire_webhook(payload, webhook_url)

    if not sns_arn and not webhook_url:
        log.warning("No alert channels configured — alert not sent")
        results["warning"] = "no channels configured"

    return results


def _fire_sns(
    payload: dict,
    subject: str,
    sns_arn: str,
    region: str,
) -> str:
    """Publish to SNS. Returns 'ok' or error string."""
    try:
        sns = boto3.client("sns", region_name=region)
        sns.publish(
            TopicArn=sns_arn,
            Subject=subject,
            Message=json.dumps(payload, indent=2),
            MessageAttributes={
                "severity": {
                    "DataType":    "String",
                    "StringValue": payload.get("severity", "HIGH"),
                },
                "outcome": {
                    "DataType":    "String",
                    "StringValue": payload.get("outcome", ""),
                },
            },
        )
        log.info(f"SNS alert sent: {subject}")
        return "ok"
    except Exception as e:
        log.error(f"SNS dispatch failed: {e}")
        return str(e)


def _fire_webhook(payload: dict, webhook_url: str) -> str:
    """POST to Trinity webhook. Returns 'ok' or error string."""
    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        log.info(f"Trinity webhook sent: {resp.status_code}")
        return "ok"
    except requests.exceptions.Timeout:
        log.error("Trinity webhook timeout")
        return "timeout"
    except Exception as e:
        log.error(f"Trinity webhook failed: {e}")
        return str(e)
