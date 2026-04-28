# =============================================================
# FILE: src/identity_resolver/sources.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Shared identity dict template used by all source modules.
# OWNER: Ravi Venugopal, Giggso Inc
# =============================================================

IDENTITY_TEMPLATE = {
    "ip":          "",
    "owner":       "",
    "email":       "",
    "department":  "",
    "mac_address": "",
    "location":    "",
    "asset_type":  "",
    "source":      "",
}


def make_identity(ip: str, source: str, **kwargs) -> dict:
    """Build a standard identity dict from any source."""
    result = dict(IDENTITY_TEMPLATE)
    result["ip"]     = ip
    result["source"] = source
    result.update(kwargs)
    return result
