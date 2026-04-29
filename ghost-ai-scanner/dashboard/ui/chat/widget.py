# =============================================================
# FILE: dashboard/ui/chat/widget.py
# VERSION: 1.1.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI chat widget — Streamlit expander UI.
#          Collapsed by default so it doesn't intrude on normal use.
#          Shows tab-specific suggested queries when no history yet.
#          S3 history loaded once per session on first open.
# DEPENDS: streamlit, chat/engine.py, chat/history.py
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
#   v1.1.0  2026-04-29  Suggestion chips per tab; help queryable.
# =============================================================

import os
from datetime import datetime, timezone

import streamlit as st

from .engine  import call_llm
from .history import load_history, append_history

_COMPANY = os.environ.get("COMPANY_NAME", "PatronAI")

# ── Per-tab suggested queries ──────────────────────────────────
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
}


def render_chat(events: list, email: str, view: str) -> None:
    """Render the 🤖 Ask AI expander at the bottom of a dashboard view.

    Collapsed by default. Opens to show rolling chat history, optional
    suggestion chips (when no prior messages), and a chat input.
    Session state keys are view-scoped so each view has its own thread.

    Args:
        events: Role-scoped event list from the current view.
        email:  Logged-in user's email (S3 history path + LLM context).
        view:   "exec" | "manager" | "support"
    """
    _hist_key    = f"_chat_hist_{view}"
    _loaded_key  = f"_chat_loaded_{view}"
    _pending_key = f"_chat_pending_{view}"

    # Consume any suggestion clicked on the previous rerun
    pending = st.session_state.pop(_pending_key, None)

    with st.expander("🤖  Ask AI about this view", expanded=False):

        # ── Load S3 history once per session per view ─────────
        if not st.session_state.get(_loaded_key):
            st.session_state[_hist_key]   = load_history(email, view)
            st.session_state[_loaded_key] = True

        history: list = st.session_state.get(_hist_key, [])

        # ── Render existing messages ───────────────────────────
        for msg in history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # ── Suggestion chips (only when no conversation yet) ───
        if not history and not pending:
            st.caption("Suggested questions — click to ask:")
            suggestions = _SUGGESTIONS.get(view, [])
            cols = st.columns(2)
            for i, q in enumerate(suggestions):
                if cols[i % 2].button(q, key=f"_sugg_{view}_{i}",
                                      use_container_width=True):
                    st.session_state[_pending_key] = q
                    st.rerun()

        # ── Chat input (always rendered — Streamlit requirement) ─
        typed = st.chat_input(
            "Ask anything about your AI security posture…",
            key=f"_chat_input_{view}")

        prompt = pending or typed
        if not prompt:
            return

        # Optimistic render — show user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        now      = datetime.now(timezone.utc).isoformat()
        user_msg = {"role": "user", "content": prompt, "ts": now}
        history.append(user_msg)

        # ── LLM call ──────────────────────────────────────────
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

        # ── Persist to S3 (errors silently swallowed) ─────────
        append_history(email, view, [user_msg, asst_msg])
