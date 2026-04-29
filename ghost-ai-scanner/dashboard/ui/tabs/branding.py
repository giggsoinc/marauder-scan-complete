# =============================================================
# FILE: dashboard/ui/tabs/branding.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Settings → Branding tab. Admin uploads a company logo
#          (PNG/JPG/SVG) which is stored at
#          s3://{bucket}/config/logo.png and embedded in all
#          generated PDF reports.
# DEPENDS: streamlit, boto3 (via _logo.py)
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import os

import streamlit as st

from ..reports._logo import fetch_logo_b64, upload_logo

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_CO     = os.environ.get("COMPANY_NAME", "PatronAI")


def render(email: str) -> None:
    """Branding settings tab — logo upload + preview."""
    st.markdown("### Branding")
    st.caption(
        "Upload a company logo to embed in all generated PDF reports. "
        "Stored at `s3://patronai/config/logo.png`."
    )

    if not _BUCKET:
        st.warning("MARAUDER_SCAN_BUCKET not configured — cannot store logo.")
        return

    # ── Current logo preview ──────────────────────────────────
    st.markdown("#### Current logo")
    b64 = fetch_logo_b64(_BUCKET, _REGION)
    if b64:
        st.markdown(
            f"<img src='data:image/png;base64,{b64}' "
            f"style='max-height:80px;border:1px solid #D0D7DE;"
            f"border-radius:6px;padding:8px;background:#fff'>",
            unsafe_allow_html=True,
        )
        st.caption("Logo is set — will appear in all PDF reports.")
    else:
        st.info("No logo uploaded yet. Reports will show a grey placeholder.")

    st.divider()

    # ── Upload new logo ───────────────────────────────────────
    st.markdown("#### Upload new logo")
    st.caption("Recommended: PNG, transparent background, min 200×200 px.")
    uploaded = st.file_uploader(
        "Choose file", type=["png", "jpg", "jpeg", "svg"],
        key="branding_logo_upload",
    )

    if uploaded is not None:
        file_bytes = uploaded.read()
        # Preview before saving
        st.markdown("**Preview:**")
        st.markdown(
            f"<img src='data:image/png;base64,"
            f"{__import__('base64').b64encode(file_bytes).decode()}' "
            f"style='max-height:80px;border:1px solid #D0D7DE;"
            f"border-radius:6px;padding:8px;background:#fff'>",
            unsafe_allow_html=True,
        )
        if st.button("💾 Save logo to S3", key="branding_save"):
            if upload_logo(file_bytes, _BUCKET, _REGION):
                st.success("Logo saved — all new reports will use this logo.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Upload failed — check S3 permissions.")

    st.divider()

    # ── Company name note ─────────────────────────────────────
    st.markdown("#### Company name")
    st.caption(
        f"Currently: **{_CO or '(not set)'}** — set via "
        "`COMPANY_NAME` environment variable in `.env`."
    )
    st.info(
        "To change the company name, update `COMPANY_NAME` in `.env` "
        "and restart the dashboard.",
        icon="ℹ️",
    )
