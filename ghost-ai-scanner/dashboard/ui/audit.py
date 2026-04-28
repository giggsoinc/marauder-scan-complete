# =============================================================
# FILE: dashboard/ui/audit.py
# VERSION: 1.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Audit trail writer — persists each settings change to S3.
#          Path: ocsf/audit/{YYYY}/{MM}/{DD}/{epoch}-setting-change.json
#          One record per changed field: user · field · old · new · ts.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v1.1.0  2026-04-27  write_user_action() for add/edit/remove user events.
# =============================================================

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

log    = logging.getLogger("patronai.ui.audit")
BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def write(email: str, field: str, old: Any, new: Any) -> None:
    """
    Write one audit record to S3.
    Silently skips if BUCKET is not set (demo mode).
    """
    if not BUCKET:
        return
    try:
        now  = datetime.now(timezone.utc)
        key  = (f"ocsf/audit/{now.year}/{now.month:02d}/{now.day:02d}/"
                f"{int(time.time())}-setting-change.json")
        body = json.dumps({
            "type":      "setting_change",
            "user":      email,
            "field":     field,
            "old_value": _safe(old),
            "new_value": _safe(new),
            "timestamp": now.isoformat(),
        }).encode()
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=BUCKET, Key=key, Body=body, ContentType="application/json",
        )
        log.info("Audit: %s changed %s", email, field)
    except Exception as exc:
        log.warning("Audit write failed (non-fatal): %s", exc)


def write_batch(email: str, changes: dict) -> None:
    """Write one audit record per changed field in the changes dict."""
    for field, (old, new) in changes.items():
        if old != new:
            write(email, field, old, new)


def write_user_action(actor: str, action: str, target_email: str,
                      old_record: Any, new_record: Any) -> None:
    """Audit a user management event (add / edit / remove).

    actor        — admin who performed the action
    action       — 'add' | 'edit' | 'remove'
    target_email — email of the affected user
    old_record   — dict before change, or None for adds
    new_record   — dict after change, or None for removes
    """
    old = {"email": target_email, **(old_record or {})} if old_record else None
    new = {"email": target_email, **(new_record or {})} if new_record else None
    write(email=actor, field=f"user_management:{action}", old=old, new=new)


def _safe(value: Any) -> Any:
    """Return value as-is if JSON-serialisable, else str()."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
