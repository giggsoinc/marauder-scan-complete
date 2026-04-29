# =============================================================
# FILE: dashboard/ui/chat/help.py
# VERSION: 1.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI product help content + get_help tool function.
#          Called by the LLM when a user asks "how does X work?"
#          or "what is PatronAI?". Returns markdown-formatted text.
#          Dispatched via engine.py like any other tool — events arg
#          is accepted but unused (uniform dispatch signature).
# AUDIT LOG:
#   v1.0.0  2026-04-29  Initial — help queryable via chat.
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


def get_help(events: list, topic: str = "") -> dict:
    """Return PatronAI product documentation for a topic.

    Args:
        events: Unused — present for uniform tool dispatch signature.
        topic:  overview | severity | agents | reports | mcp | faq.
                Empty or unrecognised value returns all sections.
    """
    t = topic.lower().strip()
    if t in _HELP:
        return {"topic": t, "content": _HELP[t]}
    return {
        "topics":  _ALL_TOPICS,
        "content": "\n\n---\n\n".join(
            f"## {k}\n{v}" for k, v in _HELP.items()),
    }
