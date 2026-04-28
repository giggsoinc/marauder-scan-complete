# =============================================================
# FILE: dashboard/ui/sidebar.py
# VERSION: 2.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc
# PURPOSE: PatronAI sidebar — role-aware view selector and links.
#          Phase 1B role model: role ∈ {exec, manager, support} +
#          orthogonal is_admin flag.
#            exec     → Exec only
#            manager  → Manager + Provider Lists
#            support  → Support + Manager (read-only) + Provider Lists
#            admin    → All views above + Settings (regardless of role)
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — extracted + de-branded from ghost_dashboard.py
#   v1.1.0  2026-04-19  Absolute Grafana URL via PUBLIC_HOST / GRAFANA_URL
#   v1.2.0  2026-04-19  Contrast fix — lighter tokens
#   v1.3.0  2026-04-19  Support role — SUPPORT_EMAILS env var
#   v1.4.0  2026-04-20  Grafana URL from S3 settings (session_state)
#   v2.0.0  2026-04-26  Phase 1B — role + is_admin matrix, options
#                       computed from role; SUPPORT_EMAILS env var dropped
#                       (replaced by users.json role field).
#   v2.1.0  2026-04-27  Mega-PR — removed LINKS section + Open dashboard
#                       link. Sidebar now: brand · radio · footer only.
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
    """
    Render sidebar and return the selected view name.
    Phase 1B role/admin matrix:
      exec     → 'exec'
      manager  → 'exec' | 'manager' | 'providers'   (manager landing default)
      support  → 'exec' | 'manager' | 'support' | 'providers'  (support default)
      admin    → 'exec' | 'manager' | 'support' | 'providers' | 'settings'
                 (admin overrides — sees ALL regardless of role; lands on
                  their role's view)
    """
    options, default_idx = _options_for(role, is_admin)

    with st.sidebar:
        try:
            st.image("assets/branding/patronai-logo.png", width=200)
        except Exception:
            st.markdown(
                '<div style="font-family:JetBrains Mono;font-size:18px;font-weight:700;'
                'color:#0D1117;letter-spacing:.05em;margin-bottom:4px;">PATRONAI</div>',
                unsafe_allow_html=True,
            )

        if _COMPANY:
            st.markdown(
                f'<div style="font-family:JetBrains Mono;font-size:10px;color:#1F2328;'
                f'margin-bottom:4px;">{_COMPANY}</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div style="font-family:JetBrains Mono;font-size:10px;color:#57606A;">'
            f'{email}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        choice = st.radio("View", options, index=default_idx,
                          label_visibility="collapsed")
        st.markdown("---")

        st.markdown(
            '<div style="font-family:JetBrains Mono;font-size:9px;color:#6E7781;'
            'position:fixed;bottom:20px;">PatronAI · v1.1.0</div>',
            unsafe_allow_html=True,
        )

    if "Support" in choice:
        return "support"
    if "Manager" in choice:
        return "manager"
    if "Settings" in choice:
        return "settings"
    if "Provider" in choice:
        return "providers"
    return "exec"


def _options_for(role: str, is_admin: bool) -> tuple:
    """Return (sidebar option labels, default index) for a given role/admin.
    Admin always sees the union of all role-tabs + Settings; default index
    points at the user's role's view so they land where they expect."""
    EXEC, MGR, SUP = "📊  Exec view", "🔧  Manager view", "🛡  Support view"
    PROV, SET      = "📋  Provider Lists", "⚙  Settings"
    if is_admin:
        opts = [EXEC, MGR, SUP, PROV, SET]
        idx  = {"exec": 0, "manager": 1, "support": 2}.get(role, 1)
        return opts, idx
    if role == "exec":
        return [EXEC], 0
    if role == "manager":
        return [MGR, PROV], 0
    if role == "support":
        return [SUP, MGR, PROV], 0
    # Unknown role — minimal menu (auth.py already blocked them, this is
    # belt-and-suspenders).
    return [EXEC], 0


# _render_links() removed 2026-04-27 — Grafana lives elsewhere; the "Open
# dashboard" link in the sidebar was redundant and visually noisy.
