# =============================================================
# FILE: dashboard/ui/chat/widget.py
# VERSION: 2.1.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI AI chat panel — rendered in a right-side column.
#          No expander wrapper; always visible as a side panel.
#          Suggestions shown only on first-ever open (not after clear).
#          CLEAR button wipes history but keeps suggestions suppressed.
# DEPENDS: streamlit, chat/engine.py, chat/history.py
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
#   v1.1.0  2026-04-29  Suggestion chips per tab; help queryable.
#   v2.0.0  2026-04-29  Right-side panel (no expander). CLEAR button.
#                       Suggestions shown once per session only.
#   v2.1.0  2026-04-29  Fix CLEAR: keep _loaded_key=True to prevent S3
#                       reload restoring cleared messages. Button label
#                       changed to "✕" (tooltip: "Clear conversation").
# =============================================================

import os
from datetime import datetime, timezone

import streamlit as st

from .engine  import call_llm
from .history import load_history, append_history

_COMPANY = os.environ.get("COMPANY_NAME", "PatronAI")

# ── Per-view suggested queries ─────────────────────────────────
_SUGGESTIONS: dict[str, list[str]] = {
    "exec": [
        "Who are my top 5 risky users?",
        "What's my critical finding count?",
        "Show shadow AI by provider",
        "Compare this week vs last week",
    ],
    "manager": [
        "Which AI tools does my team use most?",
        "Show high-risk findings by owner",
        "Which users have the most findings?",
        "What's the shadow AI census?",
    ],
    "support": [
        "Show all critical findings",
        "Which devices haven't checked in recently?",
        "Who has the most unresolved findings?",
        "Show activity from the last 24 hours",
    ],
    "home": [
        "Summarise my AI security posture",
        "What are the most urgent findings?",
        "Who are my riskiest users?",
        "Which shadow AI providers are active?",
    ],
}


def render_chat_panel(events: list, email: str, view: str) -> None:
    """Render the AI chat side panel inside a right-side column.

    Called from ghost_dashboard.py inside a col_chat column.
    No expander — panel is always visible.

    Args:
        events: Role-scoped event list from the current view.
        email:  Logged-in user's email (S3 history path + context).
        view:   "exec" | "manager" | "support" | "home"
    """
    _hist_key    = f"_chat_hist_{view}"
    _loaded_key  = f"_chat_loaded_{view}"
    _pending_key = f"_chat_pending_{view}"
    _sugg_key    = f"_chat_sugg_done_{view}"   # True once any prompt is sent

    # ── Load S3 history once per session per view ──────────────
    if not st.session_state.get(_loaded_key):
        st.session_state[_hist_key]   = load_history(email, view)
        st.session_state[_loaded_key] = True

    history: list = st.session_state.get(_hist_key, [])

    # ── Panel header — title + CLEAR ───────────────────────────
    c_title, c_clear = st.columns([3, 1])
    c_title.markdown(
        '<p style="font-family:JetBrains Mono;font-size:12px;'
        'color:#0969DA;font-weight:600;margin:0;padding:4px 0;">🤖  Ask PatronAI</p>',
        unsafe_allow_html=True,
    )
    if c_clear.button("✕", key=f"_chat_clear_{view}",
                      use_container_width=True,
                      help="Clear conversation"):
        st.session_state[_hist_key]   = []
        # Keep _loaded_key = True — do NOT reload from S3 (that would restore
        # the messages we just cleared). History is empty in session_state now.
        st.session_state[_loaded_key] = True
        # _sugg_key intentionally NOT reset — suggestions appear once only
        st.rerun()

    st.markdown(
        '<hr style="margin:4px 0 8px 0;border:none;border-top:1px solid #D0D7DE"/>',
        unsafe_allow_html=True,
    )

    # ── Render existing messages ───────────────────────────────
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Suggestion chips — first open only ────────────────────
    pending = st.session_state.pop(_pending_key, None)
    sugg_done = st.session_state.get(_sugg_key, False)

    if not sugg_done and not history and not pending:
        st.caption("Suggested questions:")
        for i, q in enumerate(_SUGGESTIONS.get(view, [])):
            if st.button(q, key=f"_sugg_{view}_{i}", use_container_width=True):
                st.session_state[_sugg_key]    = True
                st.session_state[_pending_key] = q
                st.rerun()

    # ── Chat input ─────────────────────────────────────────────
    typed  = st.chat_input("Ask anything about your AI security posture…",
                           key=f"_chat_input_{view}")
    prompt = pending or typed
    if not prompt:
        return

    st.session_state[_sugg_key] = True   # suppress suggestions permanently

    with st.chat_message("user"):
        st.markdown(prompt)

    now      = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "content": prompt, "ts": now}
    history.append(user_msg)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            engine_msgs = [{"role": m["role"], "content": m["content"]}
                           for m in history]
            try:
                answer = call_llm(engine_msgs, events, view, email, _COMPANY)
            except RuntimeError as exc:
                answer = f"⚠ {exc}"
        st.markdown(answer)

    asst_msg = {"role": "assistant", "content": answer,
                "ts": datetime.now(timezone.utc).isoformat()}
    history.append(asst_msg)
    st.session_state[_hist_key] = history
    append_history(email, view, [user_msg, asst_msg])
