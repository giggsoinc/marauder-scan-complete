# =============================================================
# FILE: dashboard/ui/tabs/users.py
# VERSION: 2.2.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Users settings tab — interactive CRUD over `s3://patronai/
#          users/users.json`. Admin-only. Lists everyone with their
#          role + admin badge + add/edit/remove actions.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — read-only env-var view
#   v2.0.0  2026-04-26  Phase 1B — interactive CRUD over UsersStore
#   v2.0.1  2026-04-26  Pulled widgets (pills + edit form) into
#                       users_widgets.py to honour the 150-LOC cap.
#   v2.1.0  2026-04-27  Audit trail: remove / add / edit all logged.
#   v2.2.0  2026-04-28  Welcome email via SES (email_utils) on add.
# =============================================================

import os
import sys

import streamlit as st

# Make src/ importable so we can reach UsersStore.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
# Make scripts/ importable for email_utils.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))

from .users_widgets import (VALID_ROLES, role_pill, admin_badge,
                             render_edit_inline)
from ..audit      import write_user_action
from ..audit_tail import render as render_audit_tail


def _store():
    """Build UsersStore from env-driven config. Returns None on error."""
    bucket = os.environ.get("MARAUDER_SCAN_BUCKET", "")
    if not bucket:
        return None
    try:
        from store.users_store import UsersStore
        return UsersStore(bucket, os.environ.get("AWS_REGION", "us-east-1"))
    except Exception as e:
        st.error(f"Cannot reach users store: {e}")
        return None


def render(email: str) -> None:
    """Top-level Users settings tab. `email` = currently logged-in admin
    (used as `added_by` on inserts). Caller already gated on admin."""
    store = _store()
    if store is None:
        st.error("Tenant storage not configured — cannot manage users.")
        return

    st.markdown("### Users")
    st.caption("Add, edit, or remove users. Admins see all views + "
               "Settings; non-admin role determines visible tabs.")

    users = store.read_all()
    _render_table(users, email, store)
    st.divider()
    _render_add_form(email, store)
    st.divider()
    render_audit_tail(field_prefix="user_management", limit=10)


def _render_table(users: dict, current_email: str, store) -> None:
    """One row per user with role pill + admin badge + Edit / Remove."""
    if not users:
        st.info("No users yet — add the first one below.")
        return
    for em in sorted(users.keys()):
        rec = users[em]
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        with c1:
            you = " · You" if em == current_email else ""
            st.markdown(
                f"<div style='font-family:JetBrains Mono;font-size:12px'>"
                f"{em}<span style='color:#57606A'>{you}</span></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(role_pill(rec.get("role", "")),
                        unsafe_allow_html=True)
        with c3:
            st.markdown(admin_badge(bool(rec.get("is_admin"))),
                        unsafe_allow_html=True)
        with c4:
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("Edit", key=f"edit_{em}"):
                    st.session_state["users_edit_target"] = em
            with ec2:
                if em == current_email:
                    st.caption("(you)")
                elif st.button("Remove", key=f"rm_{em}"):
                    old_rec = users[em].copy()
                    if store.remove(em):
                        write_user_action(current_email, "remove", em,
                                          old_record=old_rec, new_record=None)
                        st.success(f"Removed {em}")
                        st.rerun()
                    else:
                        st.error(f"Failed to remove {em}")

    target = st.session_state.get("users_edit_target")
    if target and target in users:
        render_edit_inline(target, users[target], current_email, store)


def _render_add_form(current_email: str, store) -> None:
    """Form to add a new user. Role + admin + notify checkbox + Save."""
    st.markdown("### Add user")
    c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 1])
    with c1:
        new_email = st.text_input("Email", key="add_user_email",
                                  placeholder="alice@company.com")
    with c2:
        new_role = st.selectbox("Role", VALID_ROLES, index=2,
                                key="add_user_role")
    with c3:
        new_admin = st.checkbox("Admin", key="add_user_admin", value=False)
    with c4:
        notify = st.checkbox("Notify", key="add_user_notify", value=True)
    with c5:
        st.markdown("&nbsp;")
        if st.button("Add", type="primary", key="add_user_btn"):
            if store.upsert(new_email, new_role, new_admin,
                            added_by=current_email):
                write_user_action(current_email, "add", new_email,
                                  old_record=None,
                                  new_record={"role": new_role,
                                              "is_admin": new_admin})
                st.success(f"Added {new_email.lower()}")
                if notify and new_email and "@" in new_email:
                    try:
                        from email_utils import send_welcome_email
                        ok = send_welcome_email(
                            recipient_email=new_email.lower(),
                            recipient_name=new_email.split("@")[0],
                            added_by=current_email,
                            role=new_role,
                        )
                        st.caption("✉ Welcome email sent." if ok
                                   else "⚠ Welcome email failed — check SES config.")
                    except Exception as exc:
                        st.caption(f"⚠ Email skipped: {exc}")
                st.rerun()
            else:
                st.error("Add failed — check email format and role.")
