# =============================================================
# FILE: dashboard/ui/chat/prompts.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI chat prompt templates. Isolated here so
#          tone, instructions, and snapshot format can be tuned
#          without touching engine or LLM transport code.
# DEPENDS: chat/tools.py (get_summary_stats)
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from .tools import get_summary_stats


# ── View-specific context blurbs ──────────────────────────────

_VIEW_CONTEXT = {
    "exec":    "You are in the EXECUTIVE view. Focus on strategic risk, "
               "trends, and high-severity findings relevant to leadership.",
    "manager": "You are in the MANAGER view. Focus on operational detail: "
               "inventory, pipeline health, and per-category breakdowns.",
    "support": "You are in the SUPPORT view. Focus on triage: rule health, "
               "agent coverage gaps, and actionable remediation steps.",
}


def build_system_prompt(events: list, view: str,
                        email: str, company: str) -> str:
    """Build the system prompt injected at the start of every chat turn.

    Includes:
    - Role identity (PatronAI analyst)
    - Company and current user context
    - Live snapshot stats (computed from events)
    - View-specific instruction blurb
    - Behavioural guidelines (concise, use tools, highlight critical)
    """
    s   = get_summary_stats(events)
    ctx = _VIEW_CONTEXT.get(view, "")
    co  = company or "the organisation"

    sev_str = ", ".join(
        f"{k}: {v}" for k, v in sorted(
            s["severities"].items(),
            key=lambda x: {"CRITICAL": 0, "HIGH": 1,
                           "MEDIUM": 2, "LOW": 3}.get(x[0], 9)))

    return (
        f"You are PatronAI, an AI security analyst for {co}.\n"
        f"Assisting: {email}  |  View: {view.upper()}\n\n"
        f"Live security snapshot:\n"
        f"  Total findings  : {s['total_findings']}\n"
        f"  By severity     : {sev_str or 'none'}\n"
        f"  Users monitored : {s['unique_users']}\n"
        f"  AI providers    : {s['unique_providers']}\n\n"
        f"{ctx}\n\n"
        "Guidelines:\n"
        "- Use your tools to answer accurately — do not guess from the snapshot.\n"
        "- Be concise and actionable. Bullet points for lists.\n"
        "- Prefix CRITICAL and HIGH findings with ⚠ for visibility.\n"
        "- If a question is out of scope, say so briefly.\n"
        "- Never reveal raw event data beyond what answers the question."
    )
