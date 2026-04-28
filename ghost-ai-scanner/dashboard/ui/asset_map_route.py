# =============================================================
# FILE: dashboard/ui/asset_map_route.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Tiny query-param router for the AI Asset Map page. Lifted out
#          of ghost_dashboard.py to keep that entry file under the
#          150-LOC cap. Pattern: links shaped `?view=asset_map&email=…`
#          (emitted by manager_tab_ai_inventory) take precedence over
#          whatever view the sidebar has selected.
# DEPENDS: streamlit, ui.data.load_data, ui.asset_map.render_asset_map
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================


def maybe_render_asset_map(query_params, fallback_email: str,
                           render_header) -> bool:
    """If the URL has `view=asset_map`, render the asset-map page and
    return True. Otherwise return False so the caller's normal routing
    runs. Header rendered before the map for visual continuity."""
    if query_params.get("view") != "asset_map":
        return False
    from ui.data       import load_data
    from ui.asset_map  import render_asset_map
    events, summary = load_data()
    render_header(summary)
    target = query_params.get("email", "") or fallback_email
    render_asset_map(events, target)
    return True
