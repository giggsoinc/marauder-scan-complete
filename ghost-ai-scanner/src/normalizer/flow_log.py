# =============================================================
# FILE: src/normalizer/flow_log.py
# VERSION: 1.1.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Parse VPC Flow Log lines and Zeek conn.log JSON records
#          into flat universal schema. Network layer only —
#          no process information available at this level.
#          v1.1.0: ENI denylist filter applied before normalisation.
#          Filters 5 AWS-managed ENI types (EFS/NAT/VPCE/ELB/Lambda).
# DEPENDS: normalizer.schema, normalizer.eni_filter
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial
#   v1.1.0  2026-04-19  ENI denylist filter — eni_filter.py integration
# =============================================================

import logging
import os
from datetime import datetime, timezone
from typing import Optional
from .schema import empty_event, infer_asset_type, protocol_number
from .eni_filter import (
    load_eni_patterns, load_eni_cache, cache_is_stale,
    enrich_with_metadata, is_denied_eni, eni_filtered_total,
)

log = logging.getLogger("marauder-scan.normalizer.flow_log")

# ── Module-level init — runs once per container lifecycle ─────
_BUCKET   = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION   = os.environ.get("AWS_REGION", "us-east-1")
_ACCT_ID  = os.environ.get("AWS_ACCOUNT_ID", "")

_DENYLIST_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "eni_denylist.yaml"
)
_ENI_PATTERNS: dict = load_eni_patterns(_DENYLIST_PATH)

# Warm the cache on first import if bucket is configured
if _BUCKET:
    load_eni_cache(_BUCKET, _REGION)

# Log filter totals every N rows processed
_LOG_COUNTS_EVERY = 1000
_rows_seen = 0


def _maybe_refresh_cache() -> None:
    """Refresh ENI metadata cache from S3 if TTL has expired (6h)."""
    if _BUCKET and cache_is_stale():
        log.info("ENI cache TTL expired — refreshing from S3")
        load_eni_cache(_BUCKET, _REGION)


def parse_vpc(raw: str, company: str = "") -> Optional[dict]:
    """
    Parse a VPC Flow Log line (space-separated) into flat schema.
    Default format (14+ fields):
      version account-id interface-id srcaddr dstaddr srcport dstport
      protocol packets bytes start end action log-status
    Returns None for headers, REJECT actions, denied ENIs, malformed lines.
    """
    global _rows_seen

    parts = raw.strip().split()

    # Skip header and short lines
    if len(parts) < 14 or parts[0] in ("version", "#"):
        return None

    # ── ENI denylist filter (earliest possible exit) ──────────
    eni_id = parts[2]
    _maybe_refresh_cache()
    eni_meta = enrich_with_metadata(eni_id)
    denied, reason = is_denied_eni(eni_meta, _ENI_PATTERNS, _ACCT_ID)
    if denied:
        log.debug(f"ENI filtered [{reason}]: {eni_id}")
        _rows_seen += 1
        if _rows_seen % _LOG_COUNTS_EVERY == 0:
            log.info(f"eni_filtered_total: {dict(eni_filtered_total)}")
        return None

    try:
        src_ip   = parts[3]
        dst_ip   = parts[4]
        dst_port = int(parts[6]) if parts[6] != "-" else 0
        proto    = protocol_number(parts[7])
        bytes_tx = int(parts[9]) if parts[9] != "-" else 0
        start_ts = parts[10]
        action   = parts[12]
    except (IndexError, ValueError) as e:
        log.debug(f"VPC flow log parse error: {e}")
        return None

    # Scanner only processes ACCEPT — REJECT already blocked by firewall
    if action != "ACCEPT":
        return None

    event = empty_event("vpc_flow", company)
    event["src_ip"]         = src_ip
    event["dst_ip"]         = dst_ip
    event["dst_port"]       = dst_port
    event["protocol"]       = proto
    event["bytes_out"]      = bytes_tx
    event["asset_type"]     = infer_asset_type(src_ip)
    event["cloud_provider"] = "aws"

    # Convert epoch timestamp to ISO
    try:
        event["timestamp"] = datetime.fromtimestamp(
            int(start_ts), tz=timezone.utc
        ).isoformat()
    except (ValueError, OSError):
        pass

    return event


def parse_zeek(raw: dict, company: str = "") -> Optional[dict]:
    """
    Parse a Zeek conn.log or dns.log JSON record into flat schema.
    Zeek ships structured JSON: ts, id.orig_h, id.resp_h, id.resp_p etc.
    Returns None if source IP is missing.
    """
    src_ip = raw.get("id.orig_h") or raw.get("orig_h", "")
    if not src_ip:
        return None

    event = empty_event("zeek", company)
    event["src_ip"]         = src_ip
    event["dst_ip"]         = raw.get("id.resp_h") or raw.get("resp_h", "")
    event["dst_port"]       = int(raw.get("id.resp_p") or raw.get("resp_p") or 0)
    event["protocol"]       = raw.get("proto", "tcp").upper()
    event["bytes_out"]      = int(raw.get("orig_bytes") or 0)
    event["asset_type"]     = infer_asset_type(src_ip)
    event["cloud_provider"] = "on-prem"

    if raw.get("query"):
        event["dst_domain"] = raw["query"]

    ts = raw.get("ts")
    if ts:
        try:
            event["timestamp"] = datetime.fromtimestamp(
                float(ts), tz=timezone.utc
            ).isoformat()
        except (ValueError, OSError):
            pass

    return event
