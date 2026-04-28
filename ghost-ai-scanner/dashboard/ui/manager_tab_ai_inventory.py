# =============================================================
# FILE: dashboard/ui/manager_tab_ai_inventory.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.2.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: New 5th Manager tab — AI INVENTORY. Surfaces the four Phase 1A
#          finding categories (MCP servers, agent workflows / scheduled,
#          tool registrations, vector DBs) deduped to one row per
#          (owner, device, category, provider) with LATEST observation.
#          Clicking an owner email routes to the AI Asset Map page for
#          that user.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
#   v1.0.1  2026-04-26  Pure-data helpers split into
#                       manager_tab_ai_inventory_data.py to keep this file
#                       under 150 LOC.
#   v1.1.0  2026-04-28  Replace treemap with mind-map network graph;
#                       upgrade KPI row from st.metric to clickable_metric.
#   v1.2.0  2026-04-28  User picker (st.pills) — mind map per selected user.
# =============================================================

import streamlit as st

from .helpers import sev_badge
from .manager_tab_ai_inventory_data import (
    PHASE_1A_CATEGORIES, CATEGORY_LABELS,
    phase_1a_only, dedup_latest, apply_filters, kpi_counts, owners_in,
)
from .time_fmt         import fmt as fmt_time
from .clickable_metric import clickable_metric
from .drill_panel      import render_drill_panel

_PANEL = "mindmap"


def _render_kpis(events: list) -> None:
    """Top-of-tab counters split by category — each is drillable."""
    counts = kpi_counts(events)
    c1, c2, c3, c4, c5 = st.columns(5)
    clickable_metric(c1, "MCP Servers",      counts.get("mcp_server", 0),
                     panel_key=_PANEL, drill_field="category",
                     drill_value="mcp_server")
    clickable_metric(c2, "Workflows",        counts.get("agent_workflow", 0),
                     panel_key=_PANEL, drill_field="category",
                     drill_value="agent_workflow")
    clickable_metric(c3, "Scheduled Agents", counts.get("agent_scheduled", 0),
                     panel_key=_PANEL, drill_field="category",
                     drill_value="agent_scheduled")
    clickable_metric(c4, "Tool Repos",       counts.get("tool_registration", 0),
                     panel_key=_PANEL, drill_field="category",
                     drill_value="tool_registration")
    clickable_metric(c5, "Vector DBs",       counts.get("vector_db", 0),
                     panel_key=_PANEL, drill_field="category",
                     drill_value="vector_db")


def _render_filters(events: list) -> dict:
    """Top-of-tab filter row. Returns chosen filters as a dict."""
    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
    with c1:
        sev = st.multiselect(
            "Severity", ["HIGH", "MEDIUM", "LOW", "CRITICAL"],
            default=["HIGH", "MEDIUM"], key="ai_inv_sev")
    with c2:
        cats = st.multiselect(
            "Category", list(PHASE_1A_CATEGORIES),
            default=list(PHASE_1A_CATEGORIES), key="ai_inv_cat",
            format_func=lambda c: CATEGORY_LABELS.get(c, c))
    with c3:
        owner_pick = st.selectbox(
            "Owner", ["(all)"] + owners_in(events), key="ai_inv_owner")
    with c4:
        search = st.text_input(
            "Search provider / device",
            placeholder="cursor, chroma, alice-mbp …", key="ai_inv_search")
    return {"sev": sev, "cats": cats, "owner": owner_pick, "search": search}


def _render_table(events: list) -> None:
    """Render the deduped rows as an HTML table with severity chips."""
    if not events:
        st.info("No AI assets in scope. Adjust filters or wait for next scan.")
        return
    rows = []
    for e in events[:200]:
        ts    = fmt_time(e.get("timestamp"))
        owner = e.get("email") or e.get("owner") or "—"
        host  = e.get("src_hostname") or "—"
        cat   = CATEGORY_LABELS.get(e.get("category", ""), e.get("category", ""))
        prov  = (e.get("provider") or "")[:80]
        sev   = e.get("severity") or "UNKNOWN"
        rows.append(
            f"<tr>"
            f"<td style='font-family:JetBrains Mono;font-size:11px;'>{ts}</td>"
            f"<td><a href='?view=user_detail&email={owner}' "
            f"style='color:#0969DA;text-decoration:none'>{owner}</a></td>"
            f"<td>{host}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:11px'>{cat}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:11px;color:#57606A'>{prov}</td>"
            f"<td>{sev_badge(sev)}</td>"
            f"</tr>"
        )
    st.markdown('<div class="card-title">AI ASSETS — DEDUP TO LATEST</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"<table><thead><tr>"
        f"<th>LAST SEEN</th><th>OWNER</th><th>DEVICE</th>"
        f"<th>CATEGORY</th><th>PROVIDER</th><th>SEV</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(f"Showing {min(len(events), 200)} of {len(events)} deduped rows.")


def render_ai_inventory(events: list) -> None:
    """Top-level entry called by manager_view.py."""
    from .ai_inventory_mindmap import render_mindmap
    from .filtered_table import search_box, apply_search_dicts
    base = phase_1a_only(events)
    _render_kpis(base)
    # ── User picker — mind map appears per-user ───────────────
    st.markdown('<div class="card-title">SELECT USER — AI FOOTPRINT</div>',
                unsafe_allow_html=True)
    all_owners = owners_in(base)
    sel = st.pills("User", all_owners, key="ai_inv_user_sel")
    if sel:
        ue = [e for e in base
              if (e.get("email") or e.get("owner")) == sel]
        render_mindmap(ue, panel_key="mindmap_u",
                       chart_key="ai_mindmap_user",
                       title=f"AI ASSETS — {sel} · click a node to drill")
        render_drill_panel("mindmap_u", ue, limit=100)
    else:
        st.caption("↑ Select a user above to explore their AI asset footprint.")
    q = search_box("ai_inv_global",
                   placeholder="search any field — provider / device / repo …")
    if q:
        base = apply_search_dicts(base, q)
    f = _render_filters(base)
    deduped = dedup_latest(apply_filters(
        base, f["sev"], f["cats"], f["owner"], f["search"]))
    _render_table(deduped)
