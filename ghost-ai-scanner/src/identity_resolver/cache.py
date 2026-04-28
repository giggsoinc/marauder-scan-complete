# =============================================================
# FILE: src/identity_resolver/cache.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: In-memory TTL cache for resolved IP identities.
#          Prevents repeated API calls to EC2, Identity Center
#          and AD for the same IP within a time window.
#          Not persisted — resets on container restart.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: stdlib only
# =============================================================

import time
import logging
from typing import Optional

log = logging.getLogger("marauder-scan.identity_resolver.cache")

DEFAULT_TTL_MINUTES = 15


class IdentityCache:
    """
    Simple in-memory dict cache with TTL per entry.
    Key: source IP string.
    Value: resolved identity dict + expiry timestamp.
    """

    def __init__(self, ttl_minutes: int = DEFAULT_TTL_MINUTES):
        self._store: dict = {}
        self._ttl_seconds = ttl_minutes * 60
        log.debug(f"Identity cache initialised — TTL {ttl_minutes} min")

    def get(self, ip: str) -> Optional[dict]:
        """Return cached identity if present and not expired."""
        entry = self._store.get(ip)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            # Expired — remove and return None
            del self._store[ip]
            log.debug(f"Cache expired for {ip}")
            return None
        return entry["identity"]

    def set(self, ip: str, identity: dict) -> None:
        """Cache a resolved identity with TTL stamp."""
        self._store[ip] = {
            "identity":   identity,
            "expires_at": time.time() + self._ttl_seconds,
        }
        log.debug(f"Cached identity for {ip}: {identity.get('owner', 'unknown')}")

    def invalidate(self, ip: str) -> None:
        """Force remove a cache entry — used after NAC CSV reload."""
        self._store.pop(ip, None)

    def stats(self) -> dict:
        """Return cache stats for Streamlit settings dashboard."""
        now = time.time()
        active = [
            ip for ip, e in self._store.items()
            if now <= e["expires_at"]
        ]
        return {
            "total_cached": len(self._store),
            "active":       len(active),
            "ttl_minutes":  self._ttl_seconds // 60,
        }
