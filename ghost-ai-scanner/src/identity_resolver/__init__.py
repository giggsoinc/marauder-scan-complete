# =============================================================
# FILE: src/identity_resolver/__init__.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Single resolve() entry point for identity resolution.
#          Tries four sources in priority order. First hit wins.
#          Results cached in memory for 15 minutes per IP.
# OWNER: Ravi Venugopal, Giggso Inc
# USAGE:
#   from identity_resolver import IdentityResolver
#   resolver = IdentityResolver(settings, store)
#   identity = resolver.resolve("10.0.4.112")
# =============================================================

from .resolver import IdentityResolver

__all__ = ["IdentityResolver"]
