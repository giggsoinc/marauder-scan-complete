#!/usr/bin/env python3
# =============================================================
# FILE: scripts/refresh_eni_cache.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Fetch all ENI metadata from EC2 and write to
#          s3://{BUCKET}/cache/eni_metadata.json.
#          Called inline by flow_log.py every 6h (cache TTL).
#          Also runnable standalone for manual refresh:
#            python scripts/refresh_eni_cache.py
#          Requires: MARAUDER_SCAN_BUCKET env var, boto3 IAM role.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — paginated ENI fetch, S3 write
# =============================================================

import json
import logging
import os
import sys
from datetime import datetime, timezone

import boto3

log = logging.getLogger("marauder-scan.refresh_eni_cache")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")
CACHE_KEY = "cache/eni_metadata.json"

# Fields to retain per ENI — only what the filter needs
_KEEP_FIELDS = {
    "NetworkInterfaceId", "Description", "InterfaceType",
    "RequesterManaged", "RequesterId", "OwnerId", "Status",
}


def get_account_id(sts_client) -> str:
    """Return AWS account ID via STS. Falls back to env var."""
    account = os.environ.get("AWS_ACCOUNT_ID", "")
    if account:
        return account
    try:
        return sts_client.get_caller_identity()["Account"]
    except Exception as e:
        log.warning(f"STS get_caller_identity failed: {e}")
        return ""


def fetch_eni_metadata(ec2_client) -> dict:
    """
    Paginate through all ENIs in the region.
    Returns dict keyed by ENI ID with trimmed metadata fields.
    Skips malformed pages and logs errors without aborting.
    """
    results: dict = {}
    paginator = ec2_client.get_paginator("describe_network_interfaces")
    try:
        for page in paginator.paginate():
            for eni in page.get("NetworkInterfaces", []):
                eni_id = eni.get("NetworkInterfaceId", "")
                if not eni_id:
                    continue
                results[eni_id] = {k: eni[k] for k in _KEEP_FIELDS if k in eni}
    except Exception as e:
        log.error(f"describe_network_interfaces failed: {e}")
    log.info(f"Fetched metadata for {len(results)} ENIs")
    return results


def write_cache_to_s3(s3_client, data: dict, account_id: str) -> bool:
    """
    Write ENI metadata dict to S3 as JSON.
    Stamps fetched_at and account_id for auditability.
    Returns True on success.
    """
    payload = {
        "_meta": {
            "fetched_at":  datetime.now(timezone.utc).isoformat(),
            "account_id":  account_id,
            "eni_count":   len(data),
            "region":      REGION,
        },
        "enis": data,
    }
    try:
        s3_client.put_object(
            Bucket=BUCKET,
            Key=CACHE_KEY,
            Body=json.dumps(payload, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        log.info(f"ENI cache written → s3://{BUCKET}/{CACHE_KEY} ({len(data)} ENIs)")
        return True
    except Exception as e:
        log.error(f"S3 write failed [{CACHE_KEY}]: {e}")
        return False


def run() -> bool:
    """Main entry point. Returns True on success."""
    if not BUCKET:
        log.error("MARAUDER_SCAN_BUCKET not set — cannot write cache")
        return False

    try:
        ec2 = boto3.client("ec2", region_name=REGION)
        s3  = boto3.client("s3",  region_name=REGION)
        sts = boto3.client("sts", region_name=REGION)
    except Exception as e:
        log.error(f"boto3 client init failed: {e}")
        return False

    account_id = get_account_id(sts)
    eni_data   = fetch_eni_metadata(ec2)
    return write_cache_to_s3(s3, eni_data, account_id)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
