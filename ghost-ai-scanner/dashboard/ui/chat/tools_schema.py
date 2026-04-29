# =============================================================
# FILE: dashboard/ui/chat/tools_schema.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: OpenAI-format tool definitions for the 8 PatronAI
#          chat tools. Kept separate from tools.py so the JSON
#          schema is easy to audit / extend without touching logic.
#          Consumed by engine.py; Anthropic transport converts it.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

# ── Shorthand builders ────────────────────────────────────────

def _fn(name: str, desc: str, props: dict, required: list = []) -> dict:
    """Build a single OpenAI tool definition."""
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": required}}}


_INT  = {"type": "integer"}
_STR  = {"type": "string"}
_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}

# ── TOOLS_SCHEMA — imported by engine.py ─────────────────────

TOOLS_SCHEMA: list = [
    _fn("get_summary_stats",
        "Overall AI security posture: total findings, severity breakdown, "
        "unique users monitored, unique providers detected.",
        {}),

    _fn("get_top_risky_users",
        "Top N users ranked by AI security finding count, with max severity.",
        {"n": {**_INT, "description": "Number of users to return (default 5)"}}),

    _fn("get_user_risk_profile",
        "Full risk profile for one user: providers, devices, "
        "severity breakdown, categories, latest finding timestamps.",
        {"email": _STR}, required=["email"]),

    _fn("query_findings",
        "Filtered findings list, newest-first. All parameters optional.",
        {"severity": {**_STR, "description": "CRITICAL|HIGH|MEDIUM|LOW"},
         "user":     {**_STR, "description": "Email address"},
         "category": _STR,
         "d_from":   _DATE,
         "d_to":     _DATE,
         "limit":    {**_INT, "description": "Max rows (default 20)"}}),

    _fn("get_fleet_status",
        "Fleet heartbeat summary: total devices, silent hosts (>24 h), "
        "latest event timestamp.",
        {}),

    _fn("get_shadow_ai_census",
        "Per-provider statistics: unique users, devices, first and last seen.",
        {}),

    _fn("get_recent_activity",
        "All findings observed in the last N hours.",
        {"hours": {**_INT, "description": "Look-back window (default 24)"}}),

    _fn("compare_periods",
        "Compare two date ranges: delta in finding count, "
        "new providers, new users appearing in period 2.",
        {"d1f": _DATE, "d1t": _DATE, "d2f": _DATE, "d2t": _DATE},
        required=["d1f", "d1t", "d2f", "d2t"]),

    _fn("get_help",
        "Return PatronAI product documentation. Call when the user asks "
        "'how does X work', 'what is X', or 'explain X'. "
        "Valid topics: overview, severity, agents, reports, mcp, faq. "
        "Empty topic returns all sections.",
        {"topic": {**_STR,
                   "description": "overview|severity|agents|reports|mcp|faq "
                                  "(empty = all topics)"}}),
]
