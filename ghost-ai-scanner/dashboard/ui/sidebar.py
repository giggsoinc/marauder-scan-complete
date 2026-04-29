# =============================================================
# FILE: dashboard/ui/sidebar.py
# VERSION: 2.3.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc
# PURPOSE: PatronAI sidebar — role-aware view selector and links.
#          Phase 1B role model: role ∈ {exec, manager, support} +
#          orthogonal is_admin flag.
#            exec     → Exec only
#            manager  → Manager + Provider Lists
#            support  → Support + Manager (read-only) + Provider Lists
#            admin    → All views above + Settings (regardless of role)
#          Home is shown first for all roles; default on first visit.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-26  Phase 1B role/admin matrix.
#   v2.1.0  2026-04-27  Removed LINKS section.
#   v2.2.0  2026-04-28  Add Reports nav.
#   v2.3.0  2026-04-29  Home nav; logo rendered from assets/branding/.
# =============================================================

import os
import streamlit as st

# PUBLIC_HOST — EC2 public IP or DNS, no trailing slash, no protocol
# GRAFANA_URL — full Grafana base URL; takes precedence over PUBLIC_HOST
_PUBLIC_HOST: str = os.environ.get("PUBLIC_HOST", "")
_GRAFANA_URL: str = os.environ.get("GRAFANA_URL", "")
_COMPANY:     str = os.environ.get("COMPANY_NAME", "")


def _grafana_link(path: str) -> str:
    """
    Build absolute Grafana URL.
    Priority: settings (session_state) → GRAFANA_URL env → PUBLIC_HOST env → relative.
    Relative fallback resolves to localhost in the browser — only a last resort.
    """
    # 1. Set via Settings → Alerting tab, stored in S3, loaded into session_state
    _from_settings: str = st.session_state.get("grafana_url", "")
    if _from_settings:
        return f"{_from_settings.rstrip('/')}{path}"
    # 2. GRAFANA_URL env var — full base URL
    if _GRAFANA_URL:
        return f"{_GRAFANA_URL.rstrip('/')}{path}"
    # 3. PUBLIC_HOST env var — EC2 IP/hostname, nginx proxies /grafana
    if _PUBLIC_HOST:
        return f"http://{_PUBLIC_HOST.rstrip('/')}/grafana{path}"
    # 4. Relative — works only when browser and server share the same origin
    return f"/grafana{path}"


def render(email: str, role: str, is_admin: bool) -> str:
    """Render sidebar; return selected view name.
    Home is the default on first session visit (_home_seen not set).
    Phase 1B role/admin matrix applies to subsequent navigations."""
    options, role_idx = _options_for(role, is_admin)
    # First visit → land on Home (index 0); thereafter keep role default
    if not st.session_state.get("_home_seen"):
        default_idx = 0
    else:
        default_idx = role_idx

    with st.sidebar:
        # ── Logo tile — SVG fallback, PNG preferred if present ─
        from .logo import sidebar_html as _logo_html
        st.markdown(_logo_html(), unsafe_allow_html=True)

        if _COMPANY:
            st.markdown(
                f'<div style="font-family:JetBrains Mono;font-size:10px;'
                f'color:#1F2328;margin:4px 0 0">{_COMPANY}</div>',
                unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-family:JetBrains Mono;font-size:10px;'
            f'color:#57606A;margin-bottom:2px">{email}</div>',
            unsafe_allow_html=True)
        st.markdown("---")

        choice = st.radio("View", options, index=default_idx,
                          label_visibility="collapsed")
        st.markdown("---")
        st.markdown(
            '<div style="font-family:JetBrains Mono;font-size:9px;color:#6E7781;'
            'position:fixed;bottom:20px;">PatronAI · v1.1.0</div>',
            unsafe_allow_html=True)

    # Mark as seen so next visit skips Home default
    st.session_state["_home_seen"] = True

    if "Home" in choice:    return "home"
    if "Support" in choice: return "support"
    if "Manager" in choice: return "manager"
    if "Reports" in choice: return "reports"
    if "Settings" in choice: return "settings"
    if "Provider" in choice: return "providers"
    return "exec"


def _options_for(role: str, is_admin: bool) -> tuple:
    """Return (option labels list, role-default index) for a given role/admin.
    Home is always prepended at index 0; role_idx points at the role's
    natural landing view (used after first visit).
    """
    HOME = "🏠  Home"
    EXEC, MGR, SUP = "📊  Exec view", "🔧  Manager view", "🛡  Support view"
    PROV, REP, SET = "📋  Provider Lists", "📄  Reports", "⚙  Settings"
    if is_admin:
        opts    = [HOME, EXEC, MGR, SUP, PROV, REP, SET]
        role_i  = {"exec": 1, "manager": 2, "support": 3}.get(role, 2)
        return opts, role_i
    if role == "exec":
        return [HOME, EXEC], 1
    if role == "manager":
        return [HOME, MGR, PROV, REP], 1
    if role == "support":
        return [HOME, SUP, MGR, PROV, REP], 1
    return [HOME, EXEC], 1


# _render_links() removed 2026-04-27 — Grafana lives elsewhere; the "Open
# dashboard" link in the sidebar was redundant and visually noisy.
