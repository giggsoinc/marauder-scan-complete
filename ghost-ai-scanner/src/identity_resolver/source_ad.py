# =============================================================
# FILE: src/identity_resolver/source_ad.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Resolve IP via Active Directory LDAP hostname lookup.
#          Third priority — used when Identity Center not available.
#          Requires ldap3 installed and AD config in settings.json.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: ldap3 (optional — skipped gracefully if not installed)
# =============================================================

import logging
from typing import Optional
from .sources import make_identity

log = logging.getLogger("marauder-scan.identity_resolver.ad")


def resolve(
    ip: str,
    ldap_url: str,
    base_dn: str,
) -> Optional[dict]:
    """
    Search AD for a computer object matching the source IP hostname.
    Returns identity dict or None if not found or ldap3 not installed.
    """
    if not ldap_url or not base_dn:
        log.debug("AD: ldap_url or base_dn not configured — skipped")
        return None

    try:
        from ldap3 import Server, Connection, ALL, SUBTREE
    except ImportError:
        log.debug("ldap3 not installed — AD lookup skipped")
        return None

    try:
        server = Server(ldap_url, get_info=ALL)
        conn   = Connection(server, auto_bind=True)

        # Search computer objects matching IP or hostname
        conn.search(
            search_base=base_dn,
            search_filter=f"(|(dNSHostName=*{ip}*)(cn=*{ip}*))",
            search_scope=SUBTREE,
            attributes=["cn", "department", "mail", "sAMAccountName"],
        )
        if not conn.entries:
            return None

        entry = conn.entries[0]
        return make_identity(
            ip=ip,
            source="active_directory",
            owner=str(entry.sAMAccountName or entry.cn or ""),
            department=str(entry.department or ""),
            email=str(entry.mail or ""),
            asset_type="laptop",
        )
    except Exception as e:
        log.debug(f"AD LDAP lookup failed for {ip}: {e}")
    return None
