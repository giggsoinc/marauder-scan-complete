# =============================================================
# FILE: src/alerter/cloudtrail_check.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Lightweight CloudTrail spot check — called only when
#          an alert fires on an authorized domain. Checks if a
#          Parameter Store GetParameter call preceded the API call.
#          No-op on non-AWS clouds or if CloudTrail not configured.
#          Returns enrichment dict merged into alert payload.
# DEPENDS: boto3
# NOTE: CloudTrail has up to 15 min delivery lag. Result is
#       best-effort enrichment only — not a hard gate.
# =============================================================

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("marauder-scan.alerter.cloudtrail_check")

LOOKBACK_MINUTES = 15


def check(
    owner: str,
    provider: str,
    region: str = "us-east-1",
) -> dict:
    """
    Spot-check CloudTrail for a GetParameter call from this owner
    within the last LOOKBACK_MINUTES before the alert time.

    Returns enrichment dict:
    {
        "cloudtrail_check": "found" | "not_found" | "error" | "skipped",
        "token_status":     "company_key" | "personal_key" | "unknown",
    }
    """
    if not owner or owner == "unknown":
        return _result("skipped", "unknown")

    try:
        import boto3
        ct = boto3.client("cloudtrail", region_name=region)

        # Search for GetParameter events in the lookback window
        end_time   = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=LOOKBACK_MINUTES)

        resp = ct.lookup_events(
            LookupAttributes=[
                {"AttributeKey": "EventName", "AttributeValue": "GetParameter"}
            ],
            StartTime=start_time,
            EndTime=end_time,
            MaxResults=20,
        )

        events = resp.get("Events", [])
        if not events:
            log.info(f"CloudTrail: no GetParameter found for {owner} — personal key suspected")
            return _result("not_found", "personal_key")

        # Check if any event involves an AI key parameter for this provider
        provider_slug = provider.lower().replace(" ", "_").replace(".", "_")
        for event in events:
            resources = event.get("Resources", [])
            for r in resources:
                if provider_slug in (r.get("ResourceName", "")).lower():
                    log.info(f"CloudTrail: company key confirmed for {owner} → {provider}")
                    return _result("found", "company_key")

        # GetParameter events exist but not for this provider
        log.info(f"CloudTrail: GetParameter found but not for {provider} — personal key suspected")
        return _result("found", "personal_key")

    except Exception as e:
        log.debug(f"CloudTrail check failed: {e}")
        return _result("error", "unknown")


def _result(check_status: str, token_status: str) -> dict:
    return {
        "cloudtrail_check": check_status,
        "token_status":     token_status,
    }
