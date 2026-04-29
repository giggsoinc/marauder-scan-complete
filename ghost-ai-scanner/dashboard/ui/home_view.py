# =============================================================
# FILE: dashboard/ui/home_view.py
# VERSION: 1.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Post-login welcome home page. Shown to every user on
#          first visit. Explains PatronAI, links to inline docs,
#          and surfaces the AI chat widget for immediate use.
#          Rendered when sidebar nav = "Home".
# DEPENDS: streamlit, chat/widget.py, docs/ HTML files
# AUDIT LOG:
#   v1.0.0  2026-04-29  Initial.
# =============================================================

import os
import streamlit as st
pass  # chat rendered by ghost_dashboard.py in right-side column

_CO = os.environ.get("COMPANY_NAME", "Your Organisation")

_STEPS = [
    ("🚀", "Deploy",
     "Send a one-click installer package to any device. "
     "Users authenticate with a time-locked OTP — no admin access needed."),
    ("🔍", "Discover",
     "Agents scan every 15 minutes. AI apps, browser extensions, "
     "CLI tools, and SaaS integrations are all captured automatically."),
    ("📊", "Act",
     "Risk-scored findings surface in role-based views. "
     "Drill down by user, provider, or severity — then export as PDF."),
]

_FEATURES = [
    ("🛡", "Risk Classification",
     "CRITICAL → LOW severity with configurable rules and allow-lists."),
    ("🤖", "AI-Powered Chat",
     "Ask natural-language questions about your security posture."),
    ("📄", "7 PDF Report Types",
     "Executive summary, user drill-down, compliance audit trail and more."),
    ("🔌", "MCP Server",
     "Expose PatronAI data to Claude Desktop via secure SSH transport."),
]

_DOCS = [
    ("📐", "Architecture & Chat Guide", "docs/architecture_chat_mcp.html", 820),
    ("📖", "User Guide",                "docs/user_guide.html",             820),
    ("📋", "Release Notes",             "docs/release_notes.html",          600),
]

_CARD = (
    "background:#F6F8FA;border:1px solid #D0D7DE;border-radius:10px;"
    "padding:18px 16px;height:100%;text-align:center"
)
_FEAT_CARD = (
    "background:#FFFFFF;border:1px solid #D0D7DE;border-radius:10px;"
    "padding:16px;height:100%"
)


def render(email: str, events: list = None, summary: dict = None) -> None:
    """Render the PatronAI home / welcome page."""
    events  = events  or []
    summary = summary or {}

    # ── Logo + tagline ─────────────────────────────────────────
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        from .logo import home_html as _logo_html
        st.markdown(_logo_html(220), unsafe_allow_html=True)
        st.markdown(
            '<div style="font-family:JetBrains Mono;font-size:13px;'
            'color:#57606A;text-align:center;margin-bottom:4px;">'
            'AI Security Intelligence</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-family:JetBrains Mono;font-size:11px;'
            f'color:#8B949E;text-align:center;margin-bottom:24px;">'
            f'{_CO}</div>', unsafe_allow_html=True)

    # ── How it works ───────────────────────────────────────────
    st.markdown("#### How PatronAI works")
    cols = st.columns(3)
    for col, (icon, title, desc) in zip(cols, _STEPS):
        col.markdown(
            f'<div style="{_CARD}"><div style="font-size:28px">{icon}</div>'
            f'<div style="font-family:JetBrains Mono;font-size:13px;'
            f'font-weight:700;margin:8px 0 4px">{title}</div>'
            f'<div style="font-size:12px;color:#57606A">{desc}</div></div>',
            unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Feature grid ──────────────────────────────────────────
    st.markdown("#### Capabilities")
    cols = st.columns(4)
    for col, (icon, title, desc) in zip(cols, _FEATURES):
        col.markdown(
            f'<div style="{_FEAT_CARD}"><span style="font-size:22px">{icon}</span>'
            f'<div style="font-family:JetBrains Mono;font-size:12px;'
            f'font-weight:700;margin:6px 0 4px">{title}</div>'
            f'<div style="font-size:11px;color:#57606A">{desc}</div></div>',
            unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Documentation ─────────────────────────────────────────
    st.markdown("#### Documentation")
    for icon, title, path, height in _DOCS:
        with st.expander(f"{icon}  {title}", expanded=False):
            try:
                html = open(path, encoding="utf-8").read()
                st.components.v1.html(html, height=height, scrolling=True)
            except FileNotFoundError:
                st.caption(f"Doc not found: `{path}` — run deploy first.")

    # Chat rendered in right-side column by ghost_dashboard.py
