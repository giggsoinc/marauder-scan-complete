# =============================================================
# FILE: dashboard/ui/tabs/users_widgets.py
# PROJECT: PatronAI — Phase 1B
# VERSION: 1.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Small widget helpers for the Users settings tab — role pills,
#          admin badge, and the inline edit form. Extracted from
#          dashboard/ui/tabs/users.py to honour the 150-LOC cap.
# DEPENDS: streamlit
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1B.
#   v1.1.0  2026-04-27  Audit trail on edit save.
# =============================================================

import streamlit as st

from ..audit import write_user_action

VALID_ROLES = ("exec", "manager", "support")


def role_pill(role: str) -> str:
    """Coloured pill — exec=purple, manager=blue, support=green."""
    color = {"exec": "#5E33B0", "manager": "#0969DA",
             "support": "#1A7F37"}.get(role, "#57606A")
    return (f"<span style='font-family:JetBrains Mono;font-size:11px;"
            f"padding:2px 8px;border-radius:10px;background:{color}22;"
            f"color:{color};border:1px solid {color}77'>"
            f"{role or '—'}</span>")


def admin_badge(is_admin: bool) -> str:
    """Red 'Admin' badge or em-dash for non-admins."""
    if is_admin:
        return ("<span class='badge badge-high' style='font-family:"
                "JetBrains Mono;font-size:11px'>Admin</span>")
    return "<span style='color:#57606A;font-size:11px'>—</span>"


def render_edit_inline(em: str, rec: dict, current_email: str, store) -> None:
    """Inline edit form for one user. Re-runs on save / cancel."""
    with st.expander(f"Edit · {em}", expanded=True):
        idx = (VALID_ROLES.index(rec.get("role", "support"))
               if rec.get("role") in VALID_ROLES else 2)
        new_role  = st.selectbox("Role", VALID_ROLES, index=idx,
                                 key=f"role_{em}")
        new_admin = st.checkbox(
            "Admin (full access + Settings)",
            value=bool(rec.get("is_admin")),
            key=f"admin_{em}",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save", key=f"save_{em}", type="primary"):
                if store.upsert(em, new_role, new_admin,
                                added_by=current_email):
                    write_user_action(
                        current_email, "edit", em,
                        old_record={"role": rec.get("role"),
                                    "is_admin": rec.get("is_admin")},
                        new_record={"role": new_role, "is_admin": new_admin},
                    )
                    st.session_state.pop("users_edit_target", None)
                    st.success(f"Updated {em}")
                    st.rerun()
                else:
                    st.error("Update failed — check role / email format.")
        with c2:
            if st.button("Cancel", key=f"cancel_{em}"):
                st.session_state.pop("users_edit_target", None)
                st.rerun()
