# =============================================================
# FILE: src/alerter/payload.py
# VERSION: 1.1.0
# UPDATED: 2026-04-19
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Build standardised alert payload from a flat finding event.
#          Same payload structure sent to SNS, Trinity and LogAnalyzer.
#          Flat JSON — no nested paths — any tool reads this directly.
#          hash_emails flag: SHA-256 PII fields before dispatch.
# DEPENDS: nothing — pure stdlib
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial
#   v1.1.0  2026-04-19  hash_pii() + hash_emails param for GDPR posture
# =============================================================

import hashlib
from datetime import datetime, timezone


def hash_pii(value: str) -> str:
    """SHA-256 hex of a PII string. Prefix marks it as hashed for consumers."""
    if not value:
        return value
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def build(event: dict, identity: dict, company: str = "",
          hash_emails: bool = False) -> dict:
    """
    Build a flat alert payload from a finding event and resolved identity.
    Sent to SNS subject + body, Trinity webhook POST and LogAnalyzer referral.
    Every field always present — empty string if not available.
    When hash_emails=True, owner and email are SHA-256 hashed before dispatch.
    """
    owner = identity.get("owner", event.get("src_ip", ""))
    email = identity.get("email", "")

    if hash_emails:
        owner = hash_pii(owner)
        email = hash_pii(email)

    return {
        # Source metadata
        "source":           "marauder-scan",
        "scanner_version":  event.get("scanner_version", "1.0.0"),
        "company":          company or event.get("company", ""),
        "alert_generated":  datetime.now(timezone.utc).isoformat(),

        # Alert classification
        "alert_type":       "UNAUTHORIZED_AI_TRAFFIC",
        "outcome":          event.get("outcome", ""),
        "severity":         event.get("severity", "HIGH"),
        "provider":         event.get("provider", ""),
        "category":         event.get("category", ""),

        # Network event fields (flat)
        "event_id":         event.get("event_id", ""),
        "timestamp":        event.get("timestamp", ""),
        "src_ip":           event.get("src_ip", ""),
        "dst_domain":       event.get("dst_domain", ""),
        "dst_ip":           event.get("dst_ip", ""),
        "dst_port":         event.get("dst_port", 0),
        "protocol":         event.get("protocol", ""),
        "bytes_out":        event.get("bytes_out", 0),
        "process_name":     event.get("process_name", ""),
        "log_source":       event.get("source", ""),
        "geo_country":      event.get("geo_country", ""),

        # Resolved identity (from identity_resolver)
        "owner":            owner,
        "email":            email,
        "department":       identity.get("department", ""),
        "mac_address":      identity.get("mac_address", ""),
        "asset_type":       identity.get("asset_type", ""),
        "identity_source":  identity.get("source", "fallback"),
        "pii_hashed":       hash_emails,

        # CloudTrail enrichment (filled by cloudtrail_check.py)
        "cloudtrail_check": event.get("cloudtrail_check", ""),
        "token_status":     event.get("token_status", ""),
        "notes":            event.get("notes", ""),
    }


def subject(payload: dict) -> str:
    """One-line SNS subject. Under 100 chars for email delivery."""
    return (
        f"[MARAUDER SCAN {payload['severity']}] "
        f"{payload['provider']} — "
        f"{payload['owner']} — "
        f"{payload['company']}"
    )[:100]
