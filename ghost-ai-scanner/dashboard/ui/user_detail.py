# =============================================================
# FILE: dashboard/ui/user_detail.py
# PROJECT: PatronAI — Mega-PR
# VERSION: 1.0.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Per-user detail page — opened by clicking an email or
#          agent-fleet name. Two tabs:
#            ASSETS — Treemap + table (reuses asset_map.render_asset_map)
#            LOGS   — Recent events for this user, filterable.
#          Replaces the older single-tab asset_map view; the existing
#          asset_map module stays as the Treemap/expander renderer used
#          inside the ASSETS tab here.
# DEPENDS: streamlit, asset_map, time_fmt
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Mega-PR.
# =============================================================

import streamlit as st

from .asset_map        import render_asset_map
from .time_fmt         import fmt as fmt_time
from .helpers          import sev_badge, geo_flag
from .filtered_table   import search_box, apply_search_dicts


def render_user_detail(events: list, email: str) -> None:
    """Two-tab per-user page. `events` is the full event list."""
    if not email:
        st.warning("No user selected.")
        return

    st.markdown(f"### User detail — `{email}`")
    user_events = [e for e in events
                   if (e.get("email") or e.get("owner") or "") == email]
    st.caption(f"{len(user_events)} total event(s) for this user.")

    t1, t2 = st.tabs(["  ASSETS  ", "  LOGS  "])
    with t1:
        render_asset_map(events, email)
    with t2:
        _render_logs(user_events)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("← back"):
        st.query_params.clear()
        st.rerun()


def _render_logs(user_events: list) -> None:
    """Logs tab — recent events for this user, with global search."""
    if not user_events:
        st.info("No log events for this user yet.")
        return

    q = search_box("user_detail_logs",
                   placeholder="search any column …")
    rows_in = sorted(user_events,
                     key=lambda e: e.get("timestamp", ""), reverse=True)
    rows_in = apply_search_dicts(rows_in, q)[:200]
    if not rows_in:
        st.caption("No matching events.")
        return

    rows_html = "".join(
        f"<tr>"
        f"<td style='font-family:JetBrains Mono;font-size:10px;color:#57606A'>"
        f"{fmt_time(e.get('timestamp'))}</td>"
        f"<td style='font-family:JetBrains Mono;font-size:11px'>"
        f"{e.get('src_ip', e.get('device_id', '—'))}</td>"
        f"<td style='font-family:JetBrains Mono;font-size:11px'>"
        f"{(e.get('provider') or '—')[:60]}</td>"
        f"<td>{sev_badge(e.get('severity', 'UNKNOWN'))}</td>"
        f"<td style='font-family:JetBrains Mono;font-size:10px;color:#57606A'>"
        f"{(e.get('source') or '—')[:30]}</td>"
        f"<td style='font-family:JetBrains Mono;font-size:10px'>"
        f"{geo_flag(e.get('geo_country',''))} {e.get('geo_country','')}</td>"
        f"</tr>"
        for e in rows_in
    )
    st.markdown(
        f'<div class="card-title">RECENT EVENTS — {len(rows_in)} ROWS</div>'
        f"<div style='overflow-x:auto;max-height:480px;overflow-y:auto'>"
        f"<table><thead><tr>"
        f"<th>TIMESTAMP</th><th>DEVICE / IP</th><th>PROVIDER</th>"
        f"<th>SEV</th><th>SOURCE</th><th>GEO</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>",
        unsafe_allow_html=True,
    )
