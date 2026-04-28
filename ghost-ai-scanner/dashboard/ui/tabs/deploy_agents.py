# =============================================================
# FILE: dashboard/ui/tabs/deploy_agents.py
# VERSION: 1.3.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: Streamlit admin tab for generating OTP-locked agent
#          installer packages. Shows live status table from S3.
#          Admin-only. Each submit generates one package + sends email.
#          All S3 paths delegate to AgentStore (config/HOOK_AGENTS/ prefix).
# DEPENDS: streamlit, agent_store, agent_renderer, render_agent_package
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — agent delivery system
#   v1.1.0  2026-04-19  S3 prefix update — paths now via AgentStore constant
#   v1.3.0  2026-04-20  authorized_domains field in generate form (per-user whitelist)
# =============================================================

import os
import sys
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))


def render(email: str) -> None:
    """Deploy Agents tab — generate packages and view install status."""
    st.subheader("Deploy Agents")
    st.caption(
        "Generate a personalised, OTP-locked installer for each employee. "
        "The installer sets up the PatronAI git hook agent on their device."
    )
    st.markdown("<hr>", unsafe_allow_html=True)

    _render_generate_form(email)
    st.markdown("<hr>", unsafe_allow_html=True)
    from ui.tabs.deploy_agents_table import render_status_table
    render_status_table()


def _render_generate_form(admin_email: str) -> None:
    """Form to generate a new agent package."""
    st.markdown("**Generate Installation Package**")

    with st.form("deploy_agent_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Recipient name", placeholder="Jane Smith")
        with c2:
            recipient_email = st.text_input(
                "Recipient email", placeholder="jane@company.com"
            )
        os_type = st.selectbox(
            "Target platform",
            options=["mac", "linux", "windows"],
            format_func=lambda x: {"mac": "Mac (bash)", "linux": "Linux (bash)",
                                    "windows": "Windows (PowerShell)"}[x],
        )
        auth_raw = st.text_area(
            "Authorised tools for this user (one domain per line)",
            placeholder="canva.com\nfigma.com\nnotion.so",
            height=90,
            help=(
                "Scan findings matching these domains or package names are suppressed. "
                "Leave empty to apply no exceptions. Editable later without reinstalling."
            ),
        )
        send_email = st.toggle("Send OTP via email", value=True,
                               help="Uses SES. Disable to copy OTP from the result below.")
        submitted = st.form_submit_button("Generate Package", type="primary")

    if submitted:
        if not name.strip() or not recipient_email.strip():
            st.warning("Recipient name and email are required.")
            return
        auth_domains = [d.strip() for d in auth_raw.splitlines() if d.strip()]
        _generate(name.strip(), recipient_email.strip(), os_type,
                  send_email, admin_email, auth_domains)


def _generate(name: str, email: str, os_type: str,
              send_email: bool, admin_email: str,
              authorized_domains: list | None = None) -> None:
    """Run package generation and display the result."""
    from store.agent_store import AgentStore
    from store import agent_renderer
    from render_agent_package import render_agent_package

    bucket = os.environ.get("MARAUDER_SCAN_BUCKET", "")
    region = os.environ.get("AWS_REGION", "us-east-1")

    if not bucket:
        st.error("Tenant storage not configured.")
        return

    try:
        store    = AgentStore(bucket, region)
        renderer = agent_renderer
    except Exception as e:
        st.error(f"Cannot initialise agent store: {e}")
        return

    with st.spinner(f"Generating package for {name}…"):
        try:
            result = render_agent_package(
                recipient_name     = name,
                recipient_email    = email,
                os_type            = os_type,
                store              = store,
                renderer           = renderer,
                send_email         = send_email,
                authorized_domains = authorized_domains or [],
            )
        except Exception as e:
            st.error(f"Generation failed: {e}")
            return

    if not result.get("success"):
        st.error(f"Failed: {result.get('error', 'unknown error')}")
        return

    otp     = result["otp"]
    token   = result["token"]
    dl_url  = result["installer_url"]
    emailed = result.get("email_sent", False)

    st.success(f"Package generated for **{name}** (`{email}`)")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**One-Time Password (OTP)**")
        st.text_input("OTP", value=otp, key="otp_out", label_visibility="collapsed")
        if send_email and emailed:
            st.caption("OTP sent via email.")
        elif send_email and not emailed:
            st.warning("Email failed — share OTP manually.")
    with c2:
        st.markdown("**Download Link** (48 hours)")
        st.text_input("URL", value=dl_url, key="url_out", label_visibility="collapsed")
        curl_cmd = (
            f'curl -fsSL "{dl_url}" -o setup_agent.sh '
            f'&& echo "Downloaded: $(pwd)/setup_agent.sh"'
        )
        st.code(curl_cmd, language="bash")
        st.caption("Run in Terminal — saves to your current directory and prints the path.")

    if result.get("dmg_url"):
        st.markdown("**macOS DMG** (auto-built on EC2)")
        st.markdown(f"[Download DMG]({result['dmg_url']})")
    if result.get("exe_url"):
        st.markdown("**Windows EXE** (auto-built on EC2)")
        st.markdown(f"[Download EXE]({result['exe_url']})")


