# =============================================================
# FILE: src/normalizer/nac.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Parse NAC CSV rows into flat universal schema.
#          NAC rows provide identity context — who connected from where.
#          dst_domain and dst_port are empty (NAC has no destination data).
#          Used to enrich events and provide IP-to-identity mapping.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: normalizer.schema
# =============================================================

import logging
from typing import Optional
from .schema import empty_event

log = logging.getLogger("marauder-scan.normalizer.nac")


def parse(raw: dict, company: str = "") -> Optional[dict]:
    """
    Parse a NAC CSV row (as dict from csv.DictReader) into flat schema.
    Supports both the uploaded XLS column names and simplified names.
    Returns None if no IP address found.
    """
    # Support both Excel column names and simplified names
    src_ip = (
        raw.get("IP Address")
        or raw.get("ip_address")
        or raw.get("ip", "")
    )
    if not src_ip:
        log.debug("NAC row missing IP — skipped")
        return None

    event = empty_event("nac_csv", company)

    # Identity fields — NAC is the richest source for these
    event["src_ip"]      = src_ip.strip()
    event["src_mac"]     = raw.get("MAC Address") or raw.get("mac", "")
    event["mac_address"] = event["src_mac"]
    event["src_hostname"] = (
        raw.get("Username/Device")
        or raw.get("username")
        or raw.get("device", "")
    )
    event["owner"]      = event["src_hostname"]
    event["geo_country"] = (
        raw.get("Location")
        or raw.get("location", "")
    )
    event["asset_type"] = _infer_asset_type(raw)

    # Access point context
    access_point = raw.get("Access Point") or raw.get("access_point", "")
    if access_point:
        event["src_hostname"] = event["src_hostname"] or access_point

    # NAC timestamp
    ts = (
        raw.get("Access Time")
        or raw.get("access_time")
        or raw.get("timestamp", "")
    )
    if ts:
        event["timestamp"] = str(ts)

    # NAC has no destination — these stay empty
    # dst_domain, dst_ip, dst_port, bytes_out remain at defaults

    return event


def _infer_asset_type(row: dict) -> str:
    """Infer asset type from NAC access point label."""
    ap = (row.get("Access Point") or "").lower()
    if "vpn" in ap:
        return "laptop"
    if "wifi" in ap or "wireless" in ap:
        return "laptop"
    if "firewall" in ap:
        return "ec2"
    return "laptop"
