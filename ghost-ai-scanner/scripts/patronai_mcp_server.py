#!/usr/bin/env python3
# =============================================================
# FILE: scripts/patronai_mcp_server.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI as an MCP server — exposes the same 8 analytics
#          tools to any MCP client (Claude Desktop, Cursor, etc.).
#          Loads live data from S3 at each tool call (no stale cache).
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
# DEPENDS: fastmcp, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial. SSH-only, V2 risks documented.
# =============================================================

import json
import logging
import os
import sys

# Stderr-only logging — stdout is reserved for MCP JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(levelname)s patronai_mcp %(message)s")
log = logging.getLogger("patronai.mcp")

# Resolve src/ on the path so BlobIndexStore is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, os.path.join(_HERE, "..", "dashboard"))

from fastmcp import FastMCP  # type: ignore
from ui.chat.tools import (
    get_summary_stats, get_top_risky_users, get_user_risk_profile,
    query_findings, get_fleet_status, get_shadow_ai_census,
    get_recent_activity, compare_periods,
)

mcp = FastMCP("PatronAI Security Intelligence")

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _load_events() -> list:
    """Fetch the latest events from S3 via BlobIndexStore."""
    if not _BUCKET:
        log.error("MARAUDER_SCAN_BUCKET not set")
        return []
    try:
        from blob_index_store import BlobIndexStore  # type: ignore
        store = BlobIndexStore(_BUCKET, _REGION)
        return store.events.read() or []
    except Exception as exc:
        log.error("S3 load failed: %s", exc)
        return []


def _j(obj) -> str:
    """Serialise result to a compact JSON string for MCP response."""
    return json.dumps(obj, default=str, indent=2)


# ── MCP tool registrations ────────────────────────────────────

@mcp.tool()
def summary_stats() -> str:
    """Overall AI security posture: total findings, severity breakdown,
    unique users monitored, and unique AI providers detected."""
    return _j(get_summary_stats(_load_events()))


@mcp.tool()
def top_risky_users(n: int = 5) -> str:
    """Top N users ranked by AI security finding count with max severity."""
    return _j(get_top_risky_users(_load_events(), n))


@mcp.tool()
def user_risk_profile(email: str) -> str:
    """Full risk profile for one user: providers, devices, severities."""
    return _j(get_user_risk_profile(_load_events(), email))


@mcp.tool()
def findings(severity: str = "", user: str = "", category: str = "",
             d_from: str = "", d_to: str = "", limit: int = 20) -> str:
    """Filtered findings list. All parameters optional.
    severity: CRITICAL|HIGH|MEDIUM|LOW. d_from/d_to: YYYY-MM-DD."""
    return _j(query_findings(_load_events(), severity=severity, user=user,
                             category=category, d_from=d_from,
                             d_to=d_to, limit=limit))


@mcp.tool()
def fleet_status() -> str:
    """Fleet heartbeat summary: total devices, silent hosts (>24 h)."""
    return _j(get_fleet_status(_load_events()))


@mcp.tool()
def shadow_ai_census() -> str:
    """Per-provider statistics: unique users, devices, first/last seen."""
    return _j(get_shadow_ai_census(_load_events()))


@mcp.tool()
def recent_activity(hours: int = 24) -> str:
    """All AI security findings observed in the last N hours."""
    return _j(get_recent_activity(_load_events(), hours))


@mcp.tool()
def compare_date_periods(d1f: str, d1t: str, d2f: str, d2t: str) -> str:
    """Compare two date ranges (YYYY-MM-DD). Returns delta in finding count,
    new providers, and new users appearing in the second period."""
    return _j(compare_periods(_load_events(), d1f, d1t, d2f, d2t))


if __name__ == "__main__":
    log.info("PatronAI MCP server starting (bucket=%s)", _BUCKET or "NOT SET")
    mcp.run()
