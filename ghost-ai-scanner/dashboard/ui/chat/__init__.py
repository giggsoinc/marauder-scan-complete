# =============================================================
# FILE: dashboard/ui/chat/__init__.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI chat package — re-exports the single public
#          entry point consumed by exec/manager/support views.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from .widget import render_chat_panel  # noqa: F401 — public API

# Backward-compat alias (views no longer call this directly — ghost_dashboard
# handles the column layout — but keep the alias to avoid import errors).
render_chat = render_chat_panel  # noqa: F401

__all__ = ["render_chat_panel", "render_chat"]
