# =============================================================
# FILE: dashboard/ui/chat/history.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Chat history persistence — S3 JSONL read/write.
#          Path: s3://{bucket}/chat/{sha256(email)[:16]}/{view}/YYYY-MM-DD.jsonl
#          Email is never stored in S3; SHA-256 prefix only (privacy).
#          All errors are swallowed — history failure must never
#          crash the dashboard chat widget.
# DEPENDS: boto3
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import hashlib
import json
import logging
import os
from datetime import date

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger("patronai.chat.history")

_BUCKET  = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION  = os.environ.get("AWS_REGION", "us-east-1")
_WINDOW  = 20  # max messages loaded on widget open


# ── Path helpers ──────────────────────────────────────────────

def _hash(email: str) -> str:
    """First 16 hex chars of SHA-256(email) — privacy-safe folder name."""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def _key_today(email: str, view: str) -> str:
    return f"chat/{_hash(email)}/{view}/{date.today().isoformat()}.jsonl"


def _prefix(email: str, view: str) -> str:
    return f"chat/{_hash(email)}/{view}/"


# ── Public API ────────────────────────────────────────────────

def load_history(email: str, view: str) -> list:
    """Return up to _WINDOW most-recent messages for user+view.
    Scans up to 3 daily files newest-first. Returns [] on any error."""
    bkt = _BUCKET
    if not bkt:
        return []
    try:
        s3   = boto3.client("s3", region_name=_REGION)
        resp = s3.list_objects_v2(Bucket=bkt, Prefix=_prefix(email, view))
        keys = sorted([o["Key"] for o in resp.get("Contents", [])],
                      reverse=True)
        msgs: list = []
        for key in keys[:3]:
            try:
                raw   = s3.get_object(Bucket=bkt, Key=key)["Body"].read()
                lines = [ln for ln in raw.decode().splitlines() if ln.strip()]
                for ln in reversed(lines):
                    msgs.insert(0, json.loads(ln))
                    if len(msgs) >= _WINDOW:
                        break
            except Exception:
                continue
            if len(msgs) >= _WINDOW:
                break
        return msgs[-_WINDOW:]
    except Exception as exc:
        log.warning("history load failed: %s", exc)
        return []


def append_history(email: str, view: str, messages: list) -> None:
    """Append messages to today's JSONL file. Silent on error.
    Each message is a dict with keys: role, content, ts."""
    bkt = _BUCKET
    if not bkt or not messages:
        return
    try:
        s3  = boto3.client("s3", region_name=_REGION)
        key = _key_today(email, view)
        try:
            existing = s3.get_object(Bucket=bkt, Key=key)["Body"].read().decode()
        except ClientError:
            existing = ""
        new_lines = "\n".join(json.dumps(m) for m in messages)
        body = (existing.rstrip("\n") + "\n" + new_lines).lstrip("\n")
        s3.put_object(Bucket=bkt, Key=key, Body=body.encode(),
                      ContentType="application/x-ndjson")
    except Exception as exc:
        log.warning("history append failed: %s", exc)
