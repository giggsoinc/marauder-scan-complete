# =============================================================
# FILE: src/identity_resolver/source_idc.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Resolve IAM session name to Identity Center user profile.
#          Provides display name, email and department from SSO.
#          Only runs if identity_center.enabled=true in settings.json.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: boto3
# =============================================================

import logging
from typing import Optional
import boto3
from .sources import make_identity

log = logging.getLogger("marauder-scan.identity_resolver.idc")


def resolve(
    ip: str,
    store_id: str,
    session_name: str = "",
    region: str = "us-east-1",
) -> Optional[dict]:
    """
    Look up SSO session_name in Identity Center user store.
    session_name typically contains the SSO username from CloudTrail.
    Returns identity dict or None if not found.
    """
    if not store_id or not session_name:
        log.debug("Identity Center: store_id or session_name missing — skipped")
        return None
    try:
        idc  = boto3.client("identitystore", region_name=region)
        resp = idc.list_users(
            IdentityStoreId=store_id,
            Filters=[{
                "AttributePath":  "UserName",
                "AttributeValue": session_name,
            }]
        )
        users = resp.get("Users", [])
        if not users:
            return None

        user   = users[0]
        emails = user.get("Emails", [])
        email  = emails[0].get("Value", "") if emails else ""
        name   = user.get("DisplayName") or user.get("UserName", "")

        # Department from enterprise attributes if SCIM configured
        dept = ""
        for attr in user.get("EnterpriseUserAttributes", []):
            if attr.get("Key") == "department":
                dept = attr.get("Value", "")

        return make_identity(
            ip=ip,
            source="identity_center",
            owner=name,
            email=email,
            department=dept,
        )
    except Exception as e:
        log.debug(f"Identity Center lookup failed for {ip}: {e}")
    return None
