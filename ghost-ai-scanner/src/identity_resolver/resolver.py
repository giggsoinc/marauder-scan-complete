# =============================================================
# FILE: src/identity_resolver/resolver.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Priority chain coordinator. Tries four identity sources
#          in configured order. First hit wins. Results cached.
#          Called by alerter.py at alert time only — not hot path.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: identity_resolver.sources, identity_resolver.cache
# =============================================================

import logging
from typing import Optional
from .cache      import IdentityCache
from .source_ec2 import resolve as resolve_ec2
from .source_idc import resolve as resolve_idc
from .source_ad  import resolve as resolve_ad
from .source_nac import resolve as resolve_nac

log = logging.getLogger("marauder-scan.identity_resolver.resolver")

# Default resolution priority — overridden by settings.json
DEFAULT_PRIORITY = [
    "ec2_tags",
    "identity_center",
    "active_directory",
    "nac_csv",
]


class IdentityResolver:
    """
    Resolves source IPs to employee identity.
    Called at alert time only — never in the hot scan path.
    Four sources tried in priority order. First hit wins.
    Results cached for TTL minutes to prevent repeat API calls.
    """

    def __init__(self, settings: dict, nac_df=None):
        # Identity config from settings.json
        identity_cfg  = settings.get("identity", {})
        self._priority = identity_cfg.get("priority", DEFAULT_PRIORITY)
        self._cache    = IdentityCache(
            ttl_minutes=identity_cfg.get("cache_ttl_minutes", 15)
        )
        # Config per source
        self._ec2_cfg  = identity_cfg.get("ec2_tags", {})
        self._idc_cfg  = identity_cfg.get("identity_center", {})
        self._ad_cfg   = identity_cfg.get("active_directory", {})
        self._region   = settings.get("cloud", {}).get("region", "us-east-1")

        # NAC DataFrame loaded once from S3 — passed in from main.py
        self._nac_df   = nac_df

        log.info(f"IdentityResolver ready — priority: {self._priority}")

    def resolve(self, src_ip: str) -> dict:
        """
        Resolve a source IP to an identity dict.
        Returns cached result if available.
        Falls back to IP-only dict if all sources fail.
        """
        if not src_ip:
            return self._fallback(src_ip)

        # Check cache first — avoids repeated API calls
        cached = self._cache.get(src_ip)
        if cached:
            log.debug(f"Cache hit for {src_ip}: {cached.get('owner')}")
            return cached

        # Try each source in priority order
        identity = None
        for source in self._priority:
            identity = self._try_source(source, src_ip)
            if identity:
                log.info(
                    f"Identity resolved via {source}: "
                    f"{src_ip} → {identity.get('owner', 'unknown')}"
                )
                break

        if not identity:
            log.debug(f"Identity unresolved for {src_ip} — using IP fallback")
            identity = self._fallback(src_ip)

        # Cache result regardless of source
        self._cache.set(src_ip, identity)
        return identity

    def _try_source(self, source: str, ip: str) -> Optional[dict]:
        """Dispatch to the correct source function."""
        if source == "ec2_tags" and self._ec2_cfg.get("enabled", True):
            return resolve_ec2(ip, region=self._region)

        if source == "identity_center" and self._idc_cfg.get("enabled", False):
            return resolve_idc(
                ip=ip,
                store_id=self._idc_cfg.get("store_id", ""),
                region=self._region,
            )

        if source == "active_directory" and self._ad_cfg.get("enabled", False):
            return resolve_ad(
                ip=ip,
                ldap_url=self._ad_cfg.get("ldap_url", ""),
                base_dn=self._ad_cfg.get("base_dn", ""),
            )

        if source == "nac_csv":
            return resolve_nac(ip, self._nac_df)

        return None

    def _fallback(self, ip: str) -> dict:
        """Return an IP-only identity when all sources fail."""
        return {
            "ip":          ip,
            "owner":       ip,
            "email":       "",
            "department":  "",
            "mac_address": "",
            "location":    "",
            "asset_type":  "unknown",
            "source":      "fallback",
        }

    def update_nac(self, nac_df) -> None:
        """Refresh NAC DataFrame when CSV is reloaded from S3."""
        self._nac_df = nac_df
        log.info("NAC DataFrame refreshed in IdentityResolver")

    def cache_stats(self) -> dict:
        """Expose cache stats for Streamlit settings dashboard."""
        return self._cache.stats()
