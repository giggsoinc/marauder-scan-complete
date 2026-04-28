# =============================================================
# FILE: dashboard/ui/user_detail_route.py
# PROJECT: PatronAI — Mega-PR
# VERSION: 1.0.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Tiny query-param router for the per-user detail page.
#          Takes precedence over sidebar selection when the URL has
#          `?view=user_detail&email=…`.
#          For backwards compatibility, the legacy `view=asset_map`
#          link also routes here so old bookmarks keep working.
# DEPENDS: streamlit, ui.data.load_data, ui.user_detail.render_user_detail
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Replaces asset_map_route.py.
# =============================================================


def maybe_render_user_detail(query_params, fallback_email: str,
                             render_header) -> bool:
    """Render the per-user page if URL has view=user_detail or
    (legacy) view=asset_map. Returns True iff rendered."""
    view = query_params.get("view", "")
    if view not in ("user_detail", "asset_map"):
        return False
    from ui.data         import load_data
    from ui.user_detail  import render_user_detail
    events, summary = load_data()
    render_header(summary)
    target = query_params.get("email", "") or fallback_email
    render_user_detail(events, target)
    return True
