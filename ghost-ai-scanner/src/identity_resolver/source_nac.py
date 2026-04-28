# =============================================================
# FILE: src/identity_resolver/source_nac.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Resolve IP from NAC CSV mapping Polars DataFrame.
#          Last resort fallback in the 4-step identity chain.
#          DataFrame loaded once from S3 by identity_store.py.
#          Also provides MAC address — unique to NAC source.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: polars
# =============================================================

import logging
from typing import Optional
from .sources import make_identity

log = logging.getLogger("marauder-scan.identity_resolver.nac")


def resolve(ip: str, nac_df) -> Optional[dict]:
    """
    Look up source IP in NAC mapping Polars DataFrame.
    nac_df: polars.DataFrame with columns ip, mac, username,
            department, location (loaded by identity_store.py).
    Returns identity dict or None if IP not found.
    """
    if nac_df is None or nac_df.is_empty():
        log.debug("NAC DataFrame empty — NAC fallback skipped")
        return None

    try:
        import polars as pl
        match = nac_df.filter(pl.col("ip") == ip)
        if match.is_empty():
            return None

        row = match.row(0, named=True)
        return make_identity(
            ip=ip,
            source="nac_csv",
            owner=row.get("username", ""),
            mac_address=row.get("mac", ""),
            department=row.get("department", ""),
            location=row.get("location", ""),
            asset_type="laptop",
        )
    except Exception as e:
        log.debug(f"NAC CSV lookup failed for {ip}: {e}")
    return None
