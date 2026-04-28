# =============================================================
# FILE: src/rule_health.py
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Boot-time and per-cycle rule integrity check.
#          Loads all four CSV lists, writes load_status.json sidecar
#          for the UI banner, and emits a CRITICAL self-alert
#          finding if the merged deny-list falls below threshold.
#          Strict-mode boot does NOT exit the process — degrades
#          gracefully so admins can fix from the UI.
# DEPENDS: matcher, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 6 ruleset hardening.
# =============================================================

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

from matcher import (
    load_unauthorized_full, load_authorized_full,
    load_unauthorized_code_full, load_authorized_code_full,
)

log = logging.getLogger("marauder-scan.rule_health")

BUCKET           = os.environ.get("MARAUDER_SCAN_BUCKET", "")
REGION           = os.environ.get("AWS_REGION",          "us-east-1")
STRICT_MIN_RULES = int(os.environ.get("STRICT_MIN_RULES", "50"))

LOAD_STATUS_KEY = "config/load_status.json"


def self_check_rules() -> dict:
    """
    Load all four CSV lists; write a load_status sidecar for the UI;
    fire a CRITICAL self-alert if merged deny count is below threshold.
    Returns the load_status dict.
    """
    deny,       deny_rep       = load_unauthorized_full(BUCKET)
    allow,      allow_rep      = load_authorized_full(BUCKET)
    code_deny,  code_deny_rep  = load_unauthorized_code_full(BUCKET)
    code_allow, code_allow_rep = load_authorized_code_full(BUCKET)

    status = {
        "checked_at":         datetime.now(timezone.utc).isoformat(),
        "strict_min_rules":   STRICT_MIN_RULES,
        "deny_count":         len(deny),
        "allow_count":        len(allow),
        "code_deny_count":    len(code_deny),
        "code_allow_count":   len(code_allow),
        "deny_report":        deny_rep,
        "allow_report":       allow_rep,
        "code_deny_report":   code_deny_rep,
        "code_allow_report":  code_allow_rep,
        "below_threshold":    len(deny) < STRICT_MIN_RULES,
    }

    _persist(status)
    if status["below_threshold"]:
        log.critical(
            "Rule count %d below STRICT_MIN_RULES=%d — emitting self-alert",
            len(deny), STRICT_MIN_RULES,
        )
        _emit_self_alert(status)
    else:
        log.info(
            "self_check_rules OK: deny=%d allow=%d code_deny=%d code_allow=%d",
            len(deny), len(allow), len(code_deny), len(code_allow),
        )
    return status


def _persist(status: dict) -> None:
    """Write the load_status payload to S3 for the UI banner. Non-fatal on failure."""
    try:
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=BUCKET, Key=LOAD_STATUS_KEY,
            Body=json.dumps(status, default=str).encode(),
            ContentType="application/json",
        )
    except Exception as e:
        log.warning("Failed to write %s (non-fatal): %s", LOAD_STATUS_KEY, e)


def _emit_self_alert(status: dict) -> None:
    """Write a CRITICAL finding so the existing alerter pipeline pages on degraded config."""
    now = datetime.now(timezone.utc)
    key = (f"ocsf/findings/{now.year}/{now.month:02d}/{now.day:02d}/"
           f"{int(time.time())}-degraded-rules.json")
    body = json.dumps({
        "type":      "degraded_ruleset",
        "severity":  "CRITICAL",
        "outcome":   "SELF_ALERT",
        "message":   (
            f"Rule count {status['deny_count']} below "
            f"STRICT_MIN_RULES={status['strict_min_rules']}. "
            "Matcher running on a depleted deny list."
        ),
        "status":    status,
        "timestamp": now.isoformat(),
    }, default=str).encode()
    try:
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=BUCKET, Key=key, Body=body, ContentType="application/json",
        )
        log.warning("Self-alert finding written: %s", key)
    except Exception as e:
        log.error("Self-alert write failed: %s", e)
