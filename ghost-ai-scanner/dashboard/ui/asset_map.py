# =============================================================
# FILE: dashboard/ui/asset_map.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Per-user AI ASSET MAP. Renders one person's full footprint
#          across MCP servers, agent workflows, scheduled agents, tool
#          registrations, and vector DBs as:
#            (a) a Plotly Treemap — User → Repo → Category → Asset
#            (b) a nested expander tree below
#          Dashboards reach this page via a query-param link (
#          ?view=asset_map&email=alice@x.com) emitted by the AI
#          Inventory tab's owner cells.
# DEPENDS: streamlit, plotly (already in dashboard requirements)
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

from collections import defaultdict
from typing import Iterable

import streamlit as st

from .manager_tab_ai_inventory_data import (
    PHASE_1A_CATEGORIES, CATEGORY_LABELS, phase_1a_only, dedup_latest,
)
from .time_fmt import fmt as fmt_time


def _events_for(events: Iterable[dict], email: str) -> list:
    """Filter events to one user's footprint, deduped to LATEST."""
    base = phase_1a_only(events)
    mine = [e for e in base
            if (e.get("email") or e.get("owner") or "") == email]
    return dedup_latest(mine)


def _build_treemap_data(events: list, email: str) -> tuple:
    """Build (labels, parents, values) lists for Plotly Treemap.
    Hierarchy: root(email) → repo_or_device → category → provider."""
    labels  = [email]
    parents = [""]
    values  = [len(events)]

    # Group by repo (or device when repo is missing)
    by_repo: dict = defaultdict(list)
    for e in events:
        bucket = e.get("repo_name") or e.get("src_hostname") or "(unattached)"
        by_repo[bucket].append(e)

    for repo, repo_events in by_repo.items():
        labels.append(repo)
        parents.append(email)
        values.append(len(repo_events))

        # Group by category within the repo
        by_cat: dict = defaultdict(list)
        for e in repo_events:
            by_cat[e.get("category", "")].append(e)
        for cat, cat_events in by_cat.items():
            cat_label = f"{repo} · {CATEGORY_LABELS.get(cat, cat)}"
            labels.append(cat_label)
            parents.append(repo)
            values.append(len(cat_events))

            # Leaves: providers
            for e in cat_events:
                leaf = f"{cat_label} · {(e.get('provider') or '')[:40]}"
                labels.append(leaf)
                parents.append(cat_label)
                values.append(1)
    return labels, parents, values


def _render_treemap(events: list, email: str) -> None:
    """Plotly Treemap as the primary visualisation."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("plotly is required for the treemap view — install plotly.")
        return
    if not events:
        st.info("No AI assets recorded for this user yet.")
        return
    labels, parents, values = _build_treemap_data(events, email)
    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values,
        branchvalues="total",
        hovertemplate="<b>%{label}</b><br>%{value} item(s)<extra></extra>",
        marker=dict(colorscale="Viridis", line=dict(width=0)),
    ))
    fig.update_layout(
        margin=dict(t=10, l=0, r=0, b=0),
        height=520, paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono", size=11, color="#1F2328"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_nested_expander(events: list) -> None:
    """Fallback / parallel view — a nested expander tree, repo → cat → leaves."""
    by_repo: dict = defaultdict(lambda: defaultdict(list))
    for e in events:
        bucket = e.get("repo_name") or e.get("src_hostname") or "(unattached)"
        by_repo[bucket][e.get("category", "")].append(e)
    if not by_repo:
        return
    st.markdown("### Detail tree")
    for repo, by_cat in sorted(by_repo.items()):
        total = sum(len(v) for v in by_cat.values())
        with st.expander(f"📁 {repo} — {total} asset(s)", expanded=False):
            for cat, leaves in sorted(by_cat.items()):
                st.markdown(f"**{CATEGORY_LABELS.get(cat, cat)}** "
                            f"({len(leaves)})")
                for e in leaves[:50]:
                    sev   = e.get("severity") or "UNKNOWN"
                    prov  = (e.get("provider") or "")[:80]
                    seen  = fmt_time(e.get("timestamp"))
                    st.markdown(
                        f"- `{sev}` · **{prov}** "
                        f"_(last seen {seen})_"
                    )


def render_asset_map(events: list, email: str) -> None:
    """Top-level entry. Receives the full event list + user email."""
    if not email:
        st.warning("No user selected. Click an owner cell on the AI "
                   "Inventory tab to open their map.")
        return
    user_events = _events_for(events, email)
    st.markdown(f"### AI Asset Map — `{email}`")
    st.caption(f"{len(user_events)} unique asset(s) across "
               f"{len({e.get('src_hostname','') for e in user_events})} "
               f"device(s).")
    _render_treemap(user_events, email)
    _render_nested_expander(user_events)
    if not user_events:
        return
    if st.button("← back to AI Inventory"):
        st.query_params.clear()
        st.session_state.pop("asset_map_email", None)
        st.rerun()
