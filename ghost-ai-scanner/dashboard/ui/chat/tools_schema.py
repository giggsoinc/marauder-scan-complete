# =============================================================
# FILE: dashboard/ui/chat/tools_schema.py
# VERSION: 2.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: OpenAI-format tool definitions for chat tools.
#          v2: rollup-backed; every tool exposes a `days_back`
#          time-window arg so the LLM can widen/narrow scope.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
#   v2.0.0  2026-04-29  days_back on every tool; aligned with rollups.
# =============================================================


def _fn(name: str, desc: str, props: dict, required: list = []) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": required}}}


_INT  = {"type": "integer"}
_STR  = {"type": "string"}
_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}
_DAYS = {"type": "integer",
         "description": "Look-back window in days (default 30, max 365)"}


TOOLS_SCHEMA: list = [
    _fn("get_summary_stats",
        "Overall AI security posture for the chosen window: total findings, "
        "severity breakdown, unique users monitored, unique AI providers "
        "detected. Use for a high-level snapshot.",
        {"days_back": _DAYS}),

    _fn("get_top_risky_users",
        "Top N users ranked by total weighted risk in the window. "
        "Returns email, finding count, total_risk score, max severity, "
        "top providers used.",
        {"n": {**_INT, "description": "Number of users to return (default 5)"},
         "days_back": _DAYS}),

    _fn("get_user_risk_profile",
        "Full risk profile for one user in the window: providers used, "
        "device count, severity breakdown, finding categories, first/last seen.",
        {"email": _STR, "days_back": _DAYS},
        required=["email"]),

    _fn("query_findings",
        "Aggregated findings filtered by any of: severity, user, category. "
        "Returns matching providers ranked by count (NOT raw event rows). "
        "All filters optional — empty filter set returns top-providers.",
        {"severity": {**_STR, "description": "CRITICAL|HIGH|MEDIUM|LOW"},
         "user":     {**_STR, "description": "Email address to filter by"},
         "category": {**_STR,
                      "description": "browser|package|process|ide_plugin|"
                                     "mcp_server|agent_workflow|vector_db|…"},
         "days_back": _DAYS,
         "limit":    {**_INT, "description": "Max providers (default 20)"}}),

    _fn("get_fleet_status",
        "Device activity summary in the window: total devices seen, "
        "top devices by finding count.",
        {"days_back": _DAYS}),

    _fn("get_shadow_ai_census",
        "Top AI tools / providers used in the window. Each entry has "
        "hits, user count, device count, categories where it was seen, "
        "max severity, first/last seen. Provider names are pre-normalised "
        "to human form (e.g. 'OpenAI ChatGPT', 'GitHub Copilot'). "
        "Use when the user asks 'which AI tools', 'top providers', "
        "'shadow AI census', or 'what's being used'.",
        {"days_back": _DAYS,
         "limit":     {**_INT, "description": "Max providers (default 20)"}}),

    _fn("get_recent_activity",
        "Activity in the last N hours: total findings, severity breakdown, "
        "top providers. Faster than days_back-based tools for 'today' / "
        "'last hour' style questions.",
        {"hours": {**_INT, "description": "Look-back hours (default 24)"}}),

    _fn("compare_periods",
        "Compare two date ranges: delta in finding count, "
        "new providers and new users appearing only in period 2.",
        {"d1f": _DATE, "d1t": _DATE, "d2f": _DATE, "d2t": _DATE},
        required=["d1f", "d1t", "d2f", "d2t"]),

    _fn("get_help",
        "Search PatronAI product documentation. Call this for ANY 'how do "
        "I / how to / what is / explain / uninstall / install / configure' "
        "question. PREFER `query=` (free-text BM25 search across the full "
        "HTML+MD docs) — returns the most relevant 3 passages with source "
        "filenames. Use `topic=` only for the 6 high-level sections "
        "(overview, severity, agents, reports, mcp, faq). If both are "
        "empty, returns the topic catalogue.",
        {"query": {**_STR,
                   "description": "Free-text search query, e.g. "
                                  "'how to uninstall the agent on mac', "
                                  "'install Linux agent', 'what is "
                                  "shadow AI'. Preferred over topic=."},
         "topic": {**_STR,
                   "description": "overview|severity|agents|reports|mcp|faq "
                                  "— legacy curated sections. Use query= "
                                  "for everything else."}}),

    _fn("refresh_docs",
        "Rebuild the docs RAG index if documentation files have changed "
        "since the last index build. Call this when the user says "
        "'refresh docs', 'reindex help', or after a `git pull` of new "
        "documentation. Idempotent — no-op if nothing changed. Returns "
        "status with chunk count before/after and which action was taken "
        "(reindexed | no_change | initial_load).",
        {"force": {"type": "boolean",
                   "description": "Rebuild even if no doc changed. Default false."}}),
]
