# =============================================================
# FILE: src/normalizer/schema.py
# VERSION: 2.0.0
# UPDATED: 2026-04-26
# PURPOSE: Defines the flat universal event schema.
#          Every field documented. Every field always present.
#          No nested paths. No OCSF knowledge required by consumers.
#          LogAnalyzer, Grafana, Splunk, Streamlit all read this directly.
# OWNER: Ravi Venugopal, Giggso Inc
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v2.0.0  2026-04-26  Phase 1A — added 12 optional fields covering
#                       MCP servers, agent workflows / scheduled, tool
#                       registrations, vector DBs, repo + scan metadata.
#                       Backward-compatible: every new field has a default
#                       so legacy events still serialize cleanly.
# =============================================================

import uuid
from datetime import datetime, timezone

SCANNER_VERSION = "2.0.0"

# Flat universal schema — canonical field list
FLAT_SCHEMA = {
    "event_id":        "",   # unique UUID per event
    "timestamp":       "",   # ISO 8601 UTC
    "class_uid":       4001, # OCSF Network Activity — audit trail only
    "source":          "",   # packetbeat | vpc_flow | zeek | nac_csv
    "src_ip":          "",   # source IP address
    "src_mac":         "",   # source MAC address
    "src_hostname":    "",   # source hostname
    "dst_domain":      "",   # destination domain — primary match field
    "dst_ip":          "",   # destination IP
    "dst_port":        0,    # destination port
    "protocol":        "",   # TCP | UDP | ICMP
    "bytes_out":       0,    # bytes sent to destination
    "process_name":    "",   # process making the call (Packetbeat only)
    "owner":           "",   # resolved employee identity
    "department":      "",   # resolved department
    "mac_address":     "",   # device MAC
    "geo_country":     "",   # destination country
    "asset_type":      "",   # laptop | ec2 | ecs | eks | unknown
    "cloud_provider":  "",   # aws | gcp | azure | on-prem
    "company":         "",   # company slug
    "scanner_version": SCANNER_VERSION,
    # Filled by matcher.py after normalisation
    "provider":        "",   # matched AI provider name
    "category":        "",   # matched category from unauthorized.csv
    "severity":        "",   # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    "outcome":         "",   # AUTHORIZED | UNAUTHORIZED | UNKNOWN
    # Marauder Scan — code signal fields (empty for network events)
    "code_snippet":    "",   # first 80 lines of triggering file
    "file_path":       "",   # path of triggering file on device
    "git_diff":        "",   # staged diff snippet from pre-commit hook
    "repo":            "",   # git repo name
    "branch":          "",   # git branch name
    # Phase 1A — MCP server inventory (mcp_server findings only)
    "mcp_host":        "",   # claude_desktop | cursor | continue | cline
    "config_sha256":   "",   # SHA-256 of the parent MCP config file
    "server_name":     "",   # server label as defined in mcpServers
    "command_basename": "",  # leaf executable name (no path)
    "arg_flags":       [],   # flag-shaped args only, values dropped
    "env_keys_present": [],  # env var KEYS only, values dropped
    "transport":       "",   # stdio | sse | http
    # Phase 1A — agent workflow / scheduled / tools / vector DB
    "framework":       "",   # n8n | flowise | langflow | crewai | autogen | …
    "schedule_expr":   "",   # cron string when trigger=crontab
    "kind":            "",   # vector DB kind: chroma | faiss | lancedb | …
    "scan_kind":       "",   # baseline | recurring (set by agent footer)
    "scan_id":         "",   # groups every event from one scan together
}


def empty_event(source: str, company: str = "") -> dict:
    """Return a fresh copy of the flat schema with defaults stamped."""
    event = dict(FLAT_SCHEMA)
    event["event_id"]  = str(uuid.uuid4())
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    event["source"]    = source
    event["company"]   = company
    return event


def protocol_number(proto: str) -> str:
    """Convert VPC Flow Log protocol number to name."""
    return {"6": "TCP", "17": "UDP", "1": "ICMP", "-": "UNKNOWN"}.get(
        proto, proto.upper()
    )


def infer_asset_type(ip: str) -> str:
    """Rough heuristic — RFC1918 = laptop/on-prem, else EC2."""
    if any(ip.startswith(p) for p in ("10.", "172.16.", "192.168.")):
        return "laptop"
    return "ec2"
