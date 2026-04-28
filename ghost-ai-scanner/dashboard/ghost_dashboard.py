# =============================================================
# FILE: dashboard/ghost_dashboard.py
# VERSION: 3.0.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: PatronAI User Interface — single-page Streamlit entry point.
#          Wires auth gate, sidebar, data loading, and view routing.
#          Views: Exec · Manager · Support · Settings · Provider Lists.
#          Role-based: Admin=all, Support=support+mgr+exec, User=exec+providers.
# USAGE: streamlit run dashboard/ghost_dashboard.py
# AUDIT LOG:
#   v1.0.0  2026-04-07  Initial (Pam/Steve views, synthetic data)
#   v2.0.0  2026-04-19  Rebrand — role names, dark theme, tabbed settings,
#                       ocsf_bucket fix, audit trail, no human names
#   v2.1.0  2026-04-19  Support view routing; _build_store() DRY helper
#   v3.0.0  2026-04-20  Remove is_demo / synthetic data — real data only
# =============================================================

import os
import sys
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui.auth_gate import gate
from ui.sidebar   import render as render_sidebar
from ui.styles    import inject
from ui.data      import load_data

COMPANY_NAME: str = os.environ.get("COMPANY_NAME", "")
BUCKET:       str = os.environ.get("MARAUDER_SCAN_BUCKET", "")

st.set_page_config(
    page_title="PatronAI · User Interface",
    page_icon="assets/branding/patronai-icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

inject()


# Header rendering moved to ui/header.py during Phase 1A so this entry
# file stays under the 150-LOC cap. Kept the same callable name locally
# for compatibility with existing call-sites.
from ui.header import render_header as _render_header  # noqa: E402


def _prime_grafana_url() -> None:
    """
    Load grafana_url from S3 settings into session_state once per session.
    Sidebar reads session_state so the link works without env vars.
    """
    if "grafana_url" in st.session_state:
        return
    if not BUCKET:
        return
    try:
        from blob_index_store import BlobIndexStore
        store = BlobIndexStore(BUCKET, os.environ.get("AWS_REGION", "us-east-1"))
        url = store.settings.read().get("alerts", {}).get("grafana_url", "")
        # Fall back to GRAFANA_URL env var if S3 settings don't have it
        st.session_state["grafana_url"] = url or os.environ.get("GRAFANA_URL", "")
    except Exception:
        st.session_state["grafana_url"] = os.environ.get("GRAFANA_URL", "")


def main() -> None:
    _prime_grafana_url()
    # Phase 1B — gate now returns (email, role, is_admin). Role drives
    # sidebar visibility; is_admin grants Settings + cross-persona views.
    email, role, is_admin = gate()

    # Mega-PR — query-param routing for the per-user detail page.
    # When set, takes precedence over the sidebar selection. Helper
    # extracted to ui/user_detail_route.py to honour the 150-LOC cap.
    # Legacy ?view=asset_map links route here too.
    from ui.user_detail_route import maybe_render_user_detail
    if maybe_render_user_detail(st.query_params, email, _render_header):
        return

    view = render_sidebar(email, role, is_admin)

    if view in ("exec", "manager", "providers", "support"):
        events, summary = load_data(email=email, role=role)
        _render_header(summary)

    if view == "exec":
        from ui.exec_view import render as exec_render
        exec_render(events, summary)

    elif view == "manager":
        from ui.manager_view import render as mgr_render
        mgr_render(events, summary)

    elif view == "providers":
        from ui.tabs.provider_lists import render as pl_render
        pl_render(is_admin=False, email=email)

    elif view == "support":
        _render_support(events, summary)

    elif view == "settings" and is_admin:
        _render_settings(email)


def _build_store():
    """Return (BlobIndexStore | None, error_str | None)."""
    from blob_index_store import BlobIndexStore
    R = os.environ.get("AWS_REGION", "us-east-1")
    if not BUCKET:
        return None, "Tenant storage not configured."
    try:
        return BlobIndexStore(BUCKET, R), None
    except Exception as e:
        return None, str(e)


def _render_support(events: list, summary: dict) -> None:
    """Support view — rules health, code signals, coverage, agent fleet."""
    from ui.support_view import render as support_render
    store, err = _build_store()
    if err:
        st.error(err)
    support_render(events, summary, store)

def _render_settings(email: str) -> None:
    """Tabbed settings panel — admin only."""
    store, err = _build_store()
    if err:
        st.error(err); return
    tabs = st.tabs(["Scanning", "Alerting", "Identity", "Provider Lists", "Users", "Deploy Agents"])
    from ui.tabs.scanning       import render as r_scan
    from ui.tabs.alerting       import render as r_alert
    from ui.tabs.identity       import render as r_ident
    from ui.tabs.provider_lists import render as r_prov
    from ui.tabs.users          import render as r_users
    from ui.tabs.deploy_agents  import render as r_agents

    with tabs[0]: r_scan(store, email)
    with tabs[1]: r_alert(store, email)
    with tabs[2]: r_ident(store, email)
    with tabs[3]: r_prov(is_admin=True, email=email)
    with tabs[4]: r_users(email)
    with tabs[5]: r_agents(email)


if __name__ == "__main__":
    main()
