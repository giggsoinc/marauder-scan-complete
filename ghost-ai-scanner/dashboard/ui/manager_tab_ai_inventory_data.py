# =============================================================
# FILE: dashboard/ui/manager_tab_ai_inventory_data.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Pure-data helpers for the Manager AI Inventory tab — filter,
#          dedup, KPI counts. Streamlit-free so the helpers are easy to
#          unit-test without spinning up the dashboard.
#          Extracted from manager_tab_ai_inventory.py to honour the
#          150-LOC cap when filters + KPIs + table rendering combined
#          pushed the parent file past the limit.
# DEPENDS: stdlib only
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

from collections import defaultdict
from typing import Iterable

PHASE_1A_CATEGORIES = (
    "mcp_server", "mcp_config_changed",
    "agent_workflow", "agent_scheduled",
    "tool_registration", "vector_db",
)

CATEGORY_LABELS = {
    "mcp_server":          "MCP Server",
    "mcp_config_changed":  "MCP Change",
    "agent_workflow":      "Workflow",
    "agent_scheduled":     "Scheduled",
    "tool_registration":   "Tools (code)",
    "vector_db":           "Vector DB",
}


def phase_1a_only(events: Iterable[dict]) -> list:
    """Filter raw events down to the Phase 1A categories only."""
    return [e for e in events if e.get("category") in PHASE_1A_CATEGORIES]


def dedup_latest(events: list) -> list:
    """Keep one row per (owner, device, category, provider) — LATEST timestamp.
    Returns the deduped events sorted newest-first."""
    by_key: dict = {}
    for e in events:
        key = (
            e.get("email") or e.get("owner") or "",
            e.get("src_hostname") or "",
            e.get("category") or "",
            e.get("provider") or "",
        )
        prev = by_key.get(key)
        if prev is None or e.get("timestamp", "") > prev.get("timestamp", ""):
            by_key[key] = e
    return sorted(by_key.values(),
                  key=lambda x: x.get("timestamp", ""), reverse=True)


def apply_filters(events: list, sev: list, cats: list,
                  owner: str, search: str) -> list:
    """Apply user-selected filters to the row set. Pure function."""
    out = events
    if sev:
        out = [e for e in out if (e.get("severity") or "").upper() in sev]
    if cats:
        out = [e for e in out if e.get("category") in cats]
    if owner and owner != "(all)":
        out = [e for e in out
               if (e.get("email") or e.get("owner")) == owner]
    if search:
        q = search.strip().lower()
        out = [e for e in out if q in (
            (e.get("provider") or "").lower()
            + " " + (e.get("src_hostname") or "").lower()
            + " " + (e.get("path_safe") or "").lower()
        )]
    return out


def kpi_counts(events: list) -> dict:
    """Return per-category counts for the KPI strip."""
    counts: dict = defaultdict(int)
    for e in events:
        counts[e.get("category", "")] += 1
    return dict(counts)


def owners_in(events: list) -> list:
    """Distinct owner emails present in `events` (sorted)."""
    return sorted({(e.get("email") or e.get("owner") or "")
                   for e in events
                   if (e.get("email") or e.get("owner"))})
