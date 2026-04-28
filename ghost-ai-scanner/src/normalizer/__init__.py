# =============================================================
# FILE: src/normalizer/__init__.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Auto-detect log format and route to correct parser.
#          Single normalize() function is the only import needed
#          by ingestor.py and any other consumer.
# OWNER: Ravi Venugopal, Giggso Inc
# USAGE:
#   from normalizer import normalize
#   event = normalize(raw, source_hint="packetbeat", company="giggso")
# =============================================================

import logging
from typing import Optional, Union

from .packetbeat import parse as parse_packetbeat
from .flow_log   import parse_vpc, parse_zeek
from .nac        import parse as parse_nac
from .agent      import parse as parse_agent
from .schema     import FLAT_SCHEMA, empty_event

log = logging.getLogger("marauder-scan.normalizer")


def normalize(
    raw: Union[str, dict],
    source_hint: str = "",
    company: str = "",
) -> Optional[dict]:
    """
    Auto-detect log format and normalise to flat universal schema.

    Args:
        raw:         str  → VPC Flow Log line
                     dict → Packetbeat, Zeek or NAC CSV row
        source_hint: optional hint — packetbeat | vpc_flow | zeek | nac_csv
        company:     company slug for the output event

    Returns:
        Flat event dict or None if event should be skipped.
    """
    # String input → must be a VPC Flow Log line
    if isinstance(raw, str):
        return parse_vpc(raw, company)

    if not isinstance(raw, dict):
        log.warning(f"Unsupported raw type: {type(raw)}")
        return None

    # Use hint if provided — fastest path
    if source_hint == "packetbeat":
        return parse_packetbeat(raw, company)
    if source_hint == "vpc_flow":
        return parse_vpc(str(raw), company)
    if source_hint == "zeek":
        return parse_zeek(raw, company)
    if source_hint == "nac_csv":
        return parse_nac(raw, company)
    if source_hint == "agent":
        return parse_agent(raw, company)

    # Auto-detect from field signatures
    if "@timestamp" in raw or isinstance(raw.get("source"), dict):
        return parse_packetbeat(raw, company)
    if "id.orig_h" in raw or "orig_h" in raw:
        return parse_zeek(raw, company)
    if "IP Address" in raw or "MAC Address" in raw:
        return parse_nac(raw, company)
    if "ts" in raw and "id.resp_p" in raw:
        return parse_zeek(raw, company)

    log.warning(f"Could not auto-detect log format. Keys: {list(raw.keys())[:8]}")
    return None


__all__ = ["normalize", "FLAT_SCHEMA", "empty_event"]
