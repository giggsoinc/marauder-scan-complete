# =============================================================
# FILE: src/normalizer/packetbeat.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Parse Packetbeat JSON events into flat universal schema.
#          Packetbeat captures HTTP/DNS transaction metadata per process.
#          Provides process_name — unique to endpoint-level monitoring.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: normalizer.schema
# =============================================================

import logging
from typing import Optional
from .schema import empty_event, infer_asset_type

log = logging.getLogger("marauder-scan.normalizer.packetbeat")


def parse(raw: dict, company: str = "") -> Optional[dict]:
    """
    Parse a Packetbeat JSON event into flat universal schema.
    Returns None if the event lacks minimum required fields.
    Handles both HTTP and DNS transaction types.
    """
    # Source IP — try multiple Packetbeat field paths
    src_ip = (
        (raw.get("source") or {}).get("ip")
        or (raw.get("client") or {}).get("ip")
        or raw.get("src_ip", "")
    )
    if not src_ip:
        log.debug("Packetbeat event missing source IP — skipped")
        return None

    event = empty_event("packetbeat", company)

    # Source identity fields
    src = raw.get("source") or {}
    event["src_ip"]       = src_ip
    event["src_mac"]      = src.get("mac", "")
    event["mac_address"]  = event["src_mac"]
    event["src_hostname"] = (
        src.get("domain", "")
        or (raw.get("host") or {}).get("hostname", "")
        or raw.get("src_hostname", "")
    )

    # Destination fields — HTTP, DNS or raw destination
    dst = raw.get("destination") or raw.get("server") or {}
    event["dst_ip"]   = dst.get("ip", "") or raw.get("dst_ip", "")
    event["dst_port"] = int(dst.get("port", 0) or raw.get("dst_port", 0) or 0)
    event["dst_domain"] = (
        dst.get("domain", "")
        or (raw.get("dns") or {}).get("question", {}).get("name", "")
        or (raw.get("url") or {}).get("domain", "")
        or raw.get("dst_domain", "")
    )

    # Network and transfer
    net = raw.get("network") or {}
    event["protocol"]  = (net.get("transport") or raw.get("protocol") or "tcp").upper()
    event["bytes_out"] = int(src.get("bytes", 0) or net.get("bytes", 0) or raw.get("bytes_out", 0) or 0)
    # Identity fields from flat format (pre-resolved or simulator data)
    if raw.get("owner"):
        event["owner"] = raw["owner"]
    if raw.get("department"):
        event["department"] = raw["department"]

    # Process name — Packetbeat specific, valuable for ghost AI detection
    proc = raw.get("process") or (raw.get("system") or {}).get("process") or {}
    event["process_name"] = proc.get("name", "") or raw.get("process_name", "")

    # Timestamp from event payload if present
    if raw.get("@timestamp"):
        event["timestamp"] = raw["@timestamp"]

    event["asset_type"]     = infer_asset_type(src_ip)
    event["cloud_provider"] = "aws"

    return event
