# =============================================================
# FILE: src/normalizer/eni_filter.py
# VERSION: 1.0.1
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: ENI denylist filter for VPC Flow Log normalisation.
#          Loads 5 ENI type patterns from config/eni_denylist.yaml.
#          Checks each ENI against the denylist using cached metadata.
#          Cache miss = fail open (never drop unclassified flows).
#          Filter counts logged as eni_filtered_total{reason=...}
#          (Prometheus-compatible naming — swap Counter for
#          prometheus_client.Counter when that dep is added).
# DEPENDS: pyyaml, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — 5 rule types, S3 cache, 6h refresh
#   v1.0.1  2026-04-19  Fix: load_eni_cache stored full JSON obj; extract enis key
# =============================================================

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
import yaml

log = logging.getLogger("marauder-scan.normalizer.eni_filter")

# Module-level cache — populated by load_eni_cache(), refreshed every 6h
_eni_cache:        dict              = {}
_cache_loaded_at:  Optional[datetime] = None
_CACHE_TTL_HOURS   = 6
_CACHE_S3_KEY      = "cache/eni_metadata.json"

# Prometheus-compatible filter counter: {reason: count}
eni_filtered_total: Counter = Counter()


def load_eni_patterns(path: str) -> dict:
    """
    Load ENI denylist rules from YAML file.
    Returns dict keyed by rule name (efs, nat, vpce, elb, lambda).
    Returns empty dict and logs error on any failure — caller must
    treat empty patterns as pass-through (fail open).
    """
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
        rules = data.get("rules", {})
        log.info(f"ENI denylist loaded: {len(rules)} rules from {path}")
        return rules
    except Exception as e:
        log.error(f"Failed to load ENI denylist [{path}]: {e}")
        return {}


def load_eni_cache(bucket: str, region: str = "us-east-1") -> None:
    """
    Pull cache/eni_metadata.json from S3 into module-level _eni_cache.
    Called at startup and every _CACHE_TTL_HOURS hours.
    Fails silently — stale or missing cache means fail-open filtering.
    """
    global _eni_cache, _cache_loaded_at
    try:
        s3   = boto3.client("s3", region_name=region)
        resp = s3.get_object(Bucket=bucket, Key=_CACHE_S3_KEY)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        _eni_cache       = data.get("enis", {})
        _cache_loaded_at = datetime.now(timezone.utc)
        log.info(f"ENI metadata cache loaded: {len(_eni_cache)} ENIs from s3://{bucket}/{_CACHE_S3_KEY}")
    except Exception as e:
        log.warning(f"ENI cache load failed — fail-open mode active: {e}")


def cache_is_stale() -> bool:
    """Return True if cache has never loaded or is older than TTL."""
    if _cache_loaded_at is None:
        return True
    return datetime.now(timezone.utc) - _cache_loaded_at > timedelta(hours=_CACHE_TTL_HOURS)


def enrich_with_metadata(eni_id: str) -> dict:
    """
    Look up ENI ID in module-level cache.
    Returns metadata dict on hit, empty dict on miss.
    Empty dict → caller must fail open (never drop unclassified flows).
    """
    return _eni_cache.get(eni_id, {})


def is_denied_eni(eni_meta: dict, patterns: dict, account_id: str = "") -> tuple:
    """
    Check ENI metadata against the 5 denylist rule types.
    Returns (True, reason_str) if denied, (False, "") if allowed.
    Empty eni_meta (cache miss) → always returns (False, "") — fail open.
    Increments eni_filtered_total[reason] counter on every denial.
    """
    # Cache miss — fail open, never drop unclassified flows
    if not eni_meta:
        return False, ""

    desc       = eni_meta.get("Description", "")
    iface_type = eni_meta.get("InterfaceType", "")
    req_id     = eni_meta.get("RequesterId", "")
    owner_id   = eni_meta.get("OwnerId", "")
    req_managed = eni_meta.get("RequesterManaged", False)

    # Rule 1: EFS — description prefix OR known AWS EFS requester account
    efs = patterns.get("efs", {})
    if desc.startswith(efs.get("description_prefix", "\x00")) or \
            req_id == efs.get("requester_id", ""):
        eni_filtered_total["efs"] += 1
        return True, "efs"

    # Rule 2: NAT Gateway — InterfaceType field
    if iface_type == patterns.get("nat", {}).get("interface_type", "\x00"):
        eni_filtered_total["nat"] += 1
        return True, "nat"

    # Rule 3: VPC Endpoint — InterfaceType field
    if iface_type == patterns.get("vpce", {}).get("interface_type", "\x00"):
        eni_filtered_total["vpce"] += 1
        return True, "vpce"

    # Rule 4: ELB — description prefix
    if desc.startswith(patterns.get("elb", {}).get("description_prefix", "\x00")):
        eni_filtered_total["elb"] += 1
        return True, "elb"

    # Rule 5: Lambda idle ENI — description prefix
    if desc.startswith(patterns.get("lambda", {}).get("description_prefix", "\x00")):
        eni_filtered_total["lambda"] += 1
        return True, "lambda"

    # Overarching rule: drop any other AWS-managed ENI not owned by this account
    if req_managed and account_id and owner_id != account_id:
        eni_filtered_total["managed_foreign"] += 1
        return True, "managed_foreign"

    return False, ""
