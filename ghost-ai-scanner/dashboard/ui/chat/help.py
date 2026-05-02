# =============================================================
# FILE: dashboard/ui/chat/help.py
# VERSION: 2.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI product help — two retrieval modes:
#          1. topic="agents" / "severity" / etc. → curated dict lookup
#             (backward compatible; the 6 hand-written sections stay
#              authoritative for high-level overviews).
#          2. query="how to uninstall on mac" → BM25 search over the
#             real HTML + MD docs in ghost-ai-scanner/docs/ and docs/.
#             Returns top 3 self-contained chunks. See docs_index.py.
#          Dispatched via engine.py like any other tool. The first
#          positional arg (events) is unused — kept for uniform dispatch.
# DEPENDS: docs_index (lazy-loaded BM25 over docs/**/*.{md,html})
# AUDIT LOG:
#   v1.0.0  2026-04-29  Initial — help queryable via chat.
#   v2.0.0  2026-05-02  Add `query=` path: BM25 search over the real
#                       product docs. The dashboard chat can now answer
#                       "how do I uninstall the agent on mac" etc.
#                       without hallucinating, because the doc text
#                       comes back as tool result.
# =============================================================

_HELP: dict[str, str] = {
    "overview": (
        "**PatronAI** discovers and monitors AI tools used across your "
        "organisation's devices. A lightweight agent on each machine "
        "detects AI apps, browser extensions, CLI tools, and SaaS "
        "integrations, then reports findings to your AWS S3 bucket.\n\n"
        "**Views:** Exec (strategic KPIs) · Manager (team inventory) · "
        "Support (triage, fleet, pipeline).\n\n"
        "Data never leaves your AWS account — no third-party telemetry."
    ),
    "severity": (
        "| Level | Meaning |\n|---|---|\n"
        "| **CRITICAL** | Data-exfiltration risk — unapproved AI with data access |\n"
        "| **HIGH** | Policy violation or known CVE in the tool |\n"
        "| **MEDIUM** | Unreviewed tool present, no active incident |\n"
        "| **LOW** | Informational — tool present, no current risk |\n"
        "| **CLEAN** | On the approved allowlist |\n\n"
        "Severity rules are configurable in Support → Rules."
    ),
    "agents": (
        "Agents are bash (Mac/Linux) or PowerShell (Windows) scripts.\n\n"
        "**Lifecycle:**\n"
        "1. Admin sends a package: Settings → Deploy Agents\n"
        "2. Recipient runs the installer and enters the one-time OTP\n"
        "3. Agent runs every 15 min via cron / Task Scheduler\n"
        "4. Sends heartbeat + findings to S3 over HTTPS\n\n"
        "**Status:** ONLINE < 15 min · OFFLINE > 15 min · "
        "PENDING = package sent but not yet installed.\n\n"
        "Revoke stale PENDING rows: Support → Agent Fleet → 🗑."
    ),
    "reports": (
        "**PDF reports** (sidebar → Reports):\n\n"
        "| Code | Report |\n|---|---|\n"
        "| R1 | Executive Risk Summary |\n"
        "| R2 | AI Asset Inventory |\n"
        "| R3 | User Risk Report |\n"
        "| R4 | Incident / Findings |\n"
        "| R5 | Fleet Health & Coverage |\n"
        "| R6 | Compliance Audit Trail (SHA-256 hash) |\n"
        "| R7 | Shadow AI Census |\n\n"
        "Click **👁 Preview** then **⬇ PDF** to download."
    ),
    "mcp": (
        "**PatronAI MCP Server** lets Claude Desktop and other AI agents "
        "query your security data using the same 8 analytics tools "
        "available in this chat.\n\n"
        "**Transport:** SSH stdio (V1) — no HTTP port, auth via RSA key.\n"
        "**Setup:** run `bash scripts/deploy_to_ec2.sh` → Step 6 prints "
        "the config block to paste into "
        "`~/.config/claude/claude_desktop_config.json`."
    ),
    "faq": (
        "**Why do I see duplicate agents?**\n"
        "Each deployment package gets a unique token. Multiple sends create "
        "multiple rows. Revoke stale PENDING entries from Agent Fleet.\n\n"
        "**How do I delete a ghost entry?**\n"
        "Support → Agent Fleet → 🗑 → Confirm. Action is audit-logged.\n\n"
        "**How do I switch LLM provider?**\n"
        "Set `LLM_PROVIDER=anthropic` (or `openai_compat`) via env var or "
        "AWS Parameter Store `/patronai/llm/provider`. No restart needed.\n\n"
        "**Who sees what?**\n"
        "Exec = org-wide · Manager = own team · Support = everything."
    ),
}

_ALL_TOPICS = list(_HELP.keys())


def get_help(events: list, topic: str = "", query: str = "") -> dict:
    """Return PatronAI product documentation.

    Two modes:
    - `query="..."` → BM25 search over real HTML + MD docs (preferred).
      Returns top 3 chunks with source filenames so the LLM can cite.
    - `topic="agents"` etc. → legacy curated dict lookup. Kept for
      backward compat with the 6 high-level sections.

    Empty / both empty → returns the topic catalogue (so the LLM can
    explain what topics exist).

    Args:
        events: Unused — present for uniform tool dispatch signature.
        topic:  overview | severity | agents | reports | mcp | faq.
        query:  Free-text search query. When set, takes precedence
                over `topic` and triggers BM25 retrieval.
    """
    q = (query or "").strip()
    if q:
        try:
            from .docs_index import get_index
            hits = get_index().query(q, top_k=3)
        except Exception as exc:
            return {"query": q, "error": f"docs index unavailable: {exc}",
                    "topics": _ALL_TOPICS}
        if not hits:
            return {
                "query": q,
                "matches": [],
                "_message": (f"No doc chunks matched '{q}'. Available "
                             f"high-level topics: {', '.join(_ALL_TOPICS)}. "
                             "Try a more specific phrase, or call "
                             "get_help(topic=<one of those>) for an overview."),
            }
        return {
            "query": q,
            "matches": hits,
            "_citation": {
                "source": "PatronAI docs (HTML + Markdown, BM25)",
                "files": sorted({h["source"] for h in hits}),
            },
        }

    # Legacy topic path.
    t = (topic or "").lower().strip()
    if t in _HELP:
        return {"topic": t, "content": _HELP[t]}
    return {
        "topics":  _ALL_TOPICS,
        "content": "\n\n---\n\n".join(
            f"## {k}\n{v}" for k, v in _HELP.items()),
        "_hint": ("For specific how-to questions, prefer calling "
                  "get_help(query='...') instead of topic= — it searches "
                  "the full product documentation."),
    }


def refresh_docs(events: list, force: bool = False) -> dict:
    """Rebuild the docs RAG index if any doc file's mtime has advanced
    since the last index build. Idempotent — calling repeatedly is cheap
    when nothing has changed (only stats() the files, no re-reads).

    Triggered by:
      - The user typing 'refresh docs' in the chat panel (LLM tool call).
      - The docs_refresh_loop daemon thread every 5 minutes.
      - Manual ops invocation via Streamlit admin or CLI.

    Args:
        events: Unused — uniform tool dispatch signature.
        force:  Skip the mtime check and rebuild unconditionally.
    """
    try:
        from .docs_index import get_index
        return get_index().refresh(force=bool(force))
    except Exception as exc:
        return {"action": "error", "error": f"{type(exc).__name__}: {exc}"}
