# =============================================================
# FILE: dashboard/ui/audit_tail.py
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Compact "Last N changes" viewer rendered under config tabs.
#          Reads from the existing audit/ prefix written by ui/audit.py.
#          No new infra — same S3 path, same shape, just a tail-read.
# DEPENDS: streamlit, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 6 — admin visibility on rule edits.
# =============================================================

import json
import logging
import os
from datetime import datetime

import boto3
import streamlit as st

log    = logging.getLogger("patronai.ui.audit_tail")
BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def render(field_prefix: str = "", limit: int = 5) -> None:
    """Show the last N audit objects whose `field` starts with `field_prefix`."""
    with st.expander(f"Last {limit} changes", expanded=False):
        try:
            entries = _fetch_recent(field_prefix, limit)
        except Exception as exc:
            log.warning("audit_tail fetch failed: %s", exc)
            st.caption("Audit log unavailable.")
            return
        if not entries:
            st.caption("No edits yet.")
            return
        for e in entries:
            ts = _fmt_ts(e.get("timestamp", ""))
            st.markdown(
                f"- **{ts}** · `{e.get('user','?')}` · "
                f"**{e.get('field','?')}** "
                f"({_compact(e.get('old_value'))} → {_compact(e.get('new_value'))})"
            )


def _fetch_recent(field_prefix: str, limit: int) -> list:
    """List recent audit JSON objects, filter by field prefix, return latest N."""
    s3 = boto3.client("s3", region_name=REGION)
    today = datetime.utcnow()
    prefix = f"ocsf/audit/{today.year}/{today.month:02d}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys: list = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append((obj["LastModified"], obj["Key"]))
    keys.sort(reverse=True)
    out: list = []
    for _, key in keys[: limit * 5]:  # over-fetch then filter
        try:
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            payload = json.loads(body)
            if not field_prefix or (payload.get("field") or "").startswith(field_prefix):
                out.append(payload)
                if len(out) >= limit:
                    break
        except Exception as exc:
            log.debug("Skip audit obj %s: %s", key, exc)
    return out


def _compact(value) -> str:
    """Render a value compactly for the changelog row."""
    s = str(value) if value is not None else "∅"
    return s if len(s) <= 50 else s[:47] + "…"


def _fmt_ts(iso: str) -> str:
    """Format an ISO timestamp via the central time_fmt helper —
    DD-MMM-YY HH:MM:SS TZ in the viewer's local timezone."""
    from .time_fmt import fmt as _fmt
    out = _fmt(iso)
    return out or (iso[:16] if iso else "?")
