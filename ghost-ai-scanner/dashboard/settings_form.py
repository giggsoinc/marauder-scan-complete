# =============================================================
# FILE: dashboard/settings_form.py
# VERSION: 1.1.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: PatronAI settings form — admin only.
#          Reads settings.json from S3 on load.
#          Writes settings.json to S3 on save.
#          Scanner picks up changes within one scan cycle.
# DEPENDS: streamlit, blob_index_store
# =============================================================

import os
import streamlit as st

BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")


def render(store, email: str):
    """Render the settings form and handle save."""
    st.subheader("Scanner Settings")
    settings = store.settings.read()

    with st.form("settings_form"):

        # Storage
        st.markdown("**Storage**")
        bucket = st.text_input(
            "S3 Bucket",
            value=settings.get("storage", {}).get("ocsf_bucket", BUCKET),
        )

        # Scanner timing
        st.markdown("**Scanner**")
        c1, c2 = st.columns(2)
        with c1:
            scan_interval = st.number_input(
                "Scan interval (seconds)",
                min_value=60, max_value=3600,
                value=int(settings.get("scanner", {}).get("scan_interval_secs", 300)),
            )
        with c2:
            dedup_window = st.number_input(
                "Dedup window (minutes)",
                min_value=5, max_value=1440,
                value=int(settings.get("alerts", {}).get("dedup_window_minutes", 60)),
            )

        # Alerting
        st.markdown("**Alerting**")
        c3, c4 = st.columns(2)
        with c3:
            sns_arn = st.text_input(
                "Alert channel ARN",
                value=settings.get("alerts", {}).get("sns_topic_arn", ""),
            )
        with c4:
            trinity_url = st.text_input(
                "Trinity Webhook URL",
                value=settings.get("alerts", {}).get("trinity_webhook_url", ""),
            )

        # Identity
        st.markdown("**Identity Resolution**")
        identity_cfg = settings.get("identity", {})
        priority     = identity_cfg.get("priority", ["ec2_tags","identity_center","active_directory","nac_csv"])
        st.caption(f"Priority order: {' → '.join(priority)}")

        c5, c6 = st.columns(2)
        with c5:
            idc_enabled  = st.toggle(
                "Identity Center",
                value=identity_cfg.get("identity_center", {}).get("enabled", False),
            )
            idc_store_id = st.text_input(
                "Store ID",
                value=identity_cfg.get("identity_center", {}).get("store_id", ""),
                disabled=not idc_enabled,
            )
        with c6:
            ad_enabled = st.toggle(
                "Active Directory",
                value=identity_cfg.get("active_directory", {}).get("enabled", False),
            )
            ad_ldap = st.text_input(
                "LDAP URL",
                value=identity_cfg.get("active_directory", {}).get("ldap_url", ""),
                disabled=not ad_enabled,
            )

        # Integrations
        st.markdown("**Integrations**")
        c7, c8 = st.columns(2)
        with c7:
            crowdstrike = st.toggle(
                "CrowdStrike enabled",
                value=settings.get("crowdstrike", {}).get("enabled", False),
            )
        with c8:
            cloud_provider = st.selectbox(
                "Cloud provider",
                options=["aws", "gcp", "azure"],
                index=["aws","gcp","azure"].index(
                    settings.get("cloud", {}).get("provider", "aws")
                ),
            )

        submitted = st.form_submit_button("💾 Save Settings", type="primary")

    if submitted:
        _save(store, settings, email, bucket, scan_interval, dedup_window,
              sns_arn, trinity_url, idc_enabled, idc_store_id,
              ad_enabled, ad_ldap, crowdstrike, cloud_provider)


def _save(store, settings, email, bucket, scan_interval, dedup_window,
          sns_arn, trinity_url, idc_enabled, idc_store_id,
          ad_enabled, ad_ldap, crowdstrike, cloud_provider):
    """Merge form values into settings dict and write to S3."""
    settings.setdefault("storage", {})["ocsf_bucket"]         = bucket
    settings.setdefault("scanner", {})["scan_interval_secs"]  = scan_interval
    settings.setdefault("alerts",  {})["dedup_window_minutes"] = dedup_window
    settings.setdefault("alerts",  {})["sns_topic_arn"]        = sns_arn
    settings.setdefault("alerts",  {})["trinity_webhook_url"]  = trinity_url
    settings.setdefault("crowdstrike", {})["enabled"]          = crowdstrike
    settings.setdefault("cloud",   {})["provider"]             = cloud_provider
    settings.setdefault("identity", {}).setdefault(
        "identity_center", {}
    ).update({"enabled": idc_enabled, "store_id": idc_store_id})
    settings["identity"].setdefault(
        "active_directory", {}
    ).update({"enabled": ad_enabled, "ldap_url": ad_ldap})

    ok = store.settings.write(settings, written_by=email)
    if ok:
        st.success("Settings saved. Active within one scan cycle.")
    else:
        st.error("Failed to save. Check S3 permissions.")
