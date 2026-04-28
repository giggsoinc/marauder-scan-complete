# =============================================================
# FILE: dashboard/ui/tabs/identity.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Identity settings tab — resolution priority, SSO directory,
#          LDAP source, endpoint protection toggle.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

import streamlit as st
from .. import audit as _audit


def render(store, email: str) -> None:
    """Identity resolution settings form with save and audit trail."""
    settings  = store.settings.read()
    identity  = settings.get("identity", {})
    idc_cfg   = identity.get("identity_center", {})
    ad_cfg    = identity.get("active_directory", {})

    priority = identity.get(
        "priority", ["ec2_tags", "identity_center", "active_directory", "nac_csv"]
    )
    st.markdown("**Resolution priority**")
    st.caption(
        "Order: " + " → ".join(
            {"ec2_tags": "Cloud tags", "identity_center": "SSO directory",
             "active_directory": "LDAP", "nac_csv": "Network access list"}.get(p, p)
            for p in priority
        )
    )
    st.divider()

    st.markdown("**SSO directory**")
    c1, c2 = st.columns(2)
    with c1:
        idc_enabled  = st.toggle("Enable SSO directory", value=idc_cfg.get("enabled", False))
    with c2:
        idc_store_id = st.text_input(
            "Directory store ID", value=idc_cfg.get("store_id", ""),
            disabled=not idc_enabled,
        )

    st.markdown("**LDAP source**")
    c3, c4 = st.columns(2)
    with c3:
        ad_enabled = st.toggle("Enable LDAP source", value=ad_cfg.get("enabled", False))
    with c4:
        ad_ldap = st.text_input(
            "LDAP connection URL", value=ad_cfg.get("ldap_url", ""),
            disabled=not ad_enabled,
        )

    st.markdown("**Endpoint protection**")
    crowdstrike = st.toggle(
        "Endpoint protection agent",
        value=settings.get("crowdstrike", {}).get("enabled", False),
        help="Enable process-level attribution via endpoint agent integration.",
    )

    if st.button("Save — Identity", type="primary"):
        old_idc_en  = idc_cfg.get("enabled", False)
        old_idc_sid = idc_cfg.get("store_id", "")
        old_ad_en   = ad_cfg.get("enabled", False)
        old_ad_ldap = ad_cfg.get("ldap_url", "")
        old_cs      = settings.get("crowdstrike", {}).get("enabled", False)

        settings.setdefault("identity", {}).setdefault(
            "identity_center", {}
        ).update({"enabled": idc_enabled, "store_id": idc_store_id})
        settings["identity"].setdefault("active_directory", {}).update(
            {"enabled": ad_enabled, "ldap_url": ad_ldap}
        )
        settings.setdefault("crowdstrike", {})["enabled"] = crowdstrike

        try:
            ok = store.settings.write(settings, written_by=email)
            if ok:
                changes = {
                    "idc_enabled":  (old_idc_en,  idc_enabled),
                    "idc_store_id": (old_idc_sid, idc_store_id),
                    "ad_enabled":   (old_ad_en,   ad_enabled),
                    "ad_ldap":      (old_ad_ldap, ad_ldap),
                    "crowdstrike":  (old_cs,       crowdstrike),
                }
                _audit.write_batch(email, changes)
                st.success("Identity settings saved.")
            else:
                st.error("Save failed — check tenant storage permissions.")
        except Exception as e:
            st.error(f"Save error: {e}")
