# =============================================================
# FILE: dashboard/ui/ai_inventory_treemap.py
# PROJECT: PatronAI — Mega-PR
# VERSION: 1.0.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Aggregate treemap for the Manager → AI INVENTORY tab.
#          Hierarchy: All assets → Owner → Category → Provider.
#          Sister to asset_map.py (which renders a single-user view);
#          kept separate so the data shape and color decisions can
#          diverge without breaking either consumer.
# DEPENDS: streamlit, plotly
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Mega-PR.
# =============================================================

from collections import defaultdict

import streamlit as st

from .manager_tab_ai_inventory_data import (
    phase_1a_only, dedup_latest, CATEGORY_LABELS,
)


def render_aggregate_treemap(events: list) -> None:
    """Render an aggregate treemap above the KPI counters.
    Hierarchy: root → owner → category → provider."""
    base = dedup_latest(phase_1a_only(events))
    if not base:
        return
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.caption("plotly is required for the treemap view.")
        return

    labels  = ["All AI assets"]
    parents = [""]
    values  = [len(base)]

    by_owner: dict = defaultdict(list)
    for e in base:
        owner = e.get("email") or e.get("owner") or "(unattached)"
        by_owner[owner].append(e)

    for owner, owner_events in by_owner.items():
        labels.append(owner)
        parents.append("All AI assets")
        values.append(len(owner_events))

        by_cat: dict = defaultdict(list)
        for e in owner_events:
            by_cat[e.get("category", "")].append(e)
        for cat, cat_events in by_cat.items():
            cat_label = f"{owner} · {CATEGORY_LABELS.get(cat, cat)}"
            labels.append(cat_label)
            parents.append(owner)
            values.append(len(cat_events))

            for e in cat_events:
                leaf = f"{cat_label} · {(e.get('provider') or '')[:40]}"
                labels.append(leaf)
                parents.append(cat_label)
                values.append(1)

    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values,
        branchvalues="total",
        hovertemplate="<b>%{label}</b><br>%{value} item(s)<extra></extra>",
        marker=dict(colorscale="Blues", line=dict(width=0)),
    ))
    fig.update_layout(
        margin=dict(t=10, l=0, r=0, b=0),
        height=420, paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono", size=11, color="#1F2328"),
    )
    st.markdown('<div class="card-title">AI ASSET FOOTPRINT</div>',
                unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
