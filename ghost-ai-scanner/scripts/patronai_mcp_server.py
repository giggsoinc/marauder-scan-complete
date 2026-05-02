#!/usr/bin/env python3
# =============================================================
# FILE: scripts/patronai_mcp_server.py
# VERSION: 2.0.0
# UPDATED: 2026-05-01
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI as an MCP server — exposes the same 8 analytics
#          tools to any MCP client (Claude Desktop, Cursor, etc.).
#          Reads from per-tenant hourly S3 rollups (same backend as
#          the dashboard chat panel).
#          stdout = MCP JSON-RPC only. All diagnostics → stderr.
#
# ── V1 SECURITY: SSH stdio only ──────────────────────────────
#   Transport: stdio (no HTTP port). Auth: SSH RSA key pair.
#   Access control: ~/.ssh/authorized_keys on EC2.
#   Add/revoke user = append/delete one public-key line. Instant.
#
# ── V2 RISK CALLOUTS (not in V1) ─────────────────────────────
#   ⚠ RISK-1: Inherits EC2 instance IAM role (broader than needed).
#     V2: dedicated s3:GetObject-only role for MCP process.
#   ⚠ RISK-2: No HTTP/SSE transport — SSH access required.
#     V2: SSE transport + JWT RS256 auth via Parameter Store.
#   ⚠ RISK-3: No per-call rate limiting.
#     V2: per-key rate limit to cap S3 read costs.
#
# ── Claude Desktop config (SSH) ──────────────────────────────
#   "command": "ssh",
#   "args": ["-i","~/.ssh/patronai-ec2.pem","-o",
#            "StrictHostKeyChecking=yes","ec2-user@<EC2_IP>",
#            "python /app/scripts/patronai_mcp_server.py"]
# DEPENDS: fastmcp>=3.2.0, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial. SSH-only, V2 risks documented.
#   v2.0.0  2026-05-01  Migrated chat tools to (scope, scope_id, **kwargs).
#                       Tenant scope hash derived from COMPANY_NAME env var.
#                       fastmcp pin bumped to ≥3.2.0 (CVE remediation).
# =============================================================

import json
import logging
import os
import sys

# Stderr-only logging — stdout is reserved for MCP JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(levelname)s patronai_mcp %(message)s")
log = logging.getLogger("patronai.mcp")

# Resolve src/ on the path so BlobIndexStore + chat tools are importable.
# chat/ moved out of dashboard/ in 2026-05-02 — single src/ entry now suffices.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

from fastmcp import FastMCP  # type: ignore
from chat.tools import (
    get_summary_stats, get_top_risky_users, get_user_risk_profile,
    query_findings, get_fleet_status, get_shadow_ai_census,
    get_recent_activity, compare_periods,
)
from query.rollup_reader import hash_company  # type: ignore

mcp = FastMCP("PatronAI Security Intelligence")

_BUCKET  = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION  = os.environ.get("AWS_REGION", "us-east-1")
_COMPANY = os.environ.get("COMPANY_NAME", "")

# MCP runs at tenant scope — exposes the whole company's data to the
# authenticated SSH user. Per-user (exec-view) scoping isn't applicable
# here because there's no per-call user identity in V1 stdio transport.
_SCOPE    = "tenant"
_SCOPE_ID = hash_company(_COMPANY) if _COMPANY else ""


def _j(obj) -> str:
    """Serialise result to a compact JSON string for MCP response."""
    return json.dumps(obj, default=str, indent=2)


def _ready() -> bool:
    if not _BUCKET:
        log.error("MARAUDER_SCAN_BUCKET not set")
        return False
    if not _COMPANY:
        log.error("COMPANY_NAME not set — cannot derive tenant scope_id")
        return False
    return True


# ── MCP tool registrations ────────────────────────────────────

@mcp.tool()
def summary_stats(days_back: int = 30) -> str:
    """Overall AI security posture in the window: total findings, severity
    breakdown, unique users monitored, unique AI providers detected."""
    if not _ready():
        return _j({"error": "MCP server not configured (bucket/company)"})
    return _j(get_summary_stats(_SCOPE, _SCOPE_ID, days_back=days_back))


@mcp.tool()
def top_risky_users(n: int = 5, days_back: int = 30) -> str:
    """Top N users ranked by total weighted risk in the window."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(get_top_risky_users(_SCOPE, _SCOPE_ID, n=n, days_back=days_back))


@mcp.tool()
def user_risk_profile(email: str, days_back: int = 90) -> str:
    """Full risk profile for one user in the window: providers, devices,
    severities, categories, first/last seen."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(get_user_risk_profile(_SCOPE, _SCOPE_ID,
                                     email=email, days_back=days_back))


@mcp.tool()
def findings(severity: str = "", user: str = "", category: str = "",
             days_back: int = 30, limit: int = 20) -> str:
    """Aggregated findings filtered by severity / user / category. Returns
    matching providers ranked by count from hourly rollups."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(query_findings(_SCOPE, _SCOPE_ID,
                             severity=severity, user=user,
                             category=category, days_back=days_back,
                             limit=limit))


@mcp.tool()
def fleet_status(days_back: int = 7) -> str:
    """Device activity summary in the window: total devices, top devices
    by finding count."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(get_fleet_status(_SCOPE, _SCOPE_ID, days_back=days_back))


@mcp.tool()
def shadow_ai_census(days_back: int = 90, limit: int = 20) -> str:
    """Top AI providers in the window with hits, user count, severities,
    first/last seen. Names are pre-normalised to human form."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(get_shadow_ai_census(_SCOPE, _SCOPE_ID,
                                    days_back=days_back, limit=limit))


@mcp.tool()
def recent_activity(hours: int = 24) -> str:
    """Findings observed in the last N hours: severity breakdown +
    top providers."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(get_recent_activity(_SCOPE, _SCOPE_ID, hours=hours))


@mcp.tool()
def compare_date_periods(d1f: str, d1t: str, d2f: str, d2t: str) -> str:
    """Compare two date ranges (YYYY-MM-DD). Returns delta in finding count,
    new providers, and new users appearing only in the second period."""
    if not _ready():
        return _j({"error": "MCP server not configured"})
    return _j(compare_periods(_SCOPE, _SCOPE_ID,
                              d1f=d1f, d1t=d1t, d2f=d2f, d2t=d2t))


if __name__ == "__main__":
    log.info("PatronAI MCP server starting "
             "(bucket=%s, company=%s, scope_id=%s)",
             _BUCKET or "NOT SET",
             _COMPANY or "NOT SET",
             (_SCOPE_ID[:8] + "…") if _SCOPE_ID else "NOT SET")
    mcp.run()
