# =============================================================
# FILE: src/normalizer/agent_explode.py
# PROJECT: PatronAI
# VERSION: 1.1.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Turn one ENDPOINT_SCAN payload into N flat events — one per
#          finding. The pipeline writes each to the findings store so
#          the inventory dashboard shows them as proper rows.
#          Clean scans (no findings) return [] — heartbeat covers liveness;
#          we don't bloat storage with "scan ran fine" rows.
# DEPENDS: normalizer.schema, normalizer.agent (for _bind_identity)
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Step 0.5 — make endpoint findings visible.
#   v1.1.0  2026-04-26  Phase 1A. Added 4 new finding categories
#                       (mcp_server, agent_workflow, agent_scheduled,
#                       tool_registration, vector_db) to _FINDING_SEVERITY
#                       and _provider_for(). Identity bundle untouched.
# =============================================================

import json
import logging

from .schema import empty_event

log = logging.getLogger("marauder-scan.normalizer.agent_explode")

# Severity tier per finding type. Drives alerter routing — HIGH+ goes to
# SNS / Trinity / SES; MEDIUM/LOW land on dashboard only.
_FINDING_SEVERITY = {
    # legacy categories
    "browser":              "HIGH",      # active visit to AI service
    "process":              "HIGH",      # AI tool actively running
    "container_log_signal": "HIGH",      # AI traffic/keys observed in container
    "package":              "MEDIUM",    # installed but maybe unused
    "ide_plugin":           "MEDIUM",    # installed but maybe unused
    "container_image":      "MEDIUM",    # image pulled, may not be running
    "shell_history":        "LOW",       # past command, may be ephemeral
    # Phase 1A additions
    "mcp_server":           "HIGH",      # shell-level access via MCP transport
    "agent_workflow":       "HIGH",      # autonomous loop configured to run
    "agent_scheduled":      "HIGH",      # cron / launchd-triggered AI agent
    "tool_registration":    "MEDIUM",    # @tool decorators in code (capability)
    "vector_db":            "MEDIUM",    # local RAG store; data exposure risk
}


def _scan_id(raw: dict) -> str:
    """Stable ID grouping every finding from the same scan back to its origin."""
    return f"{raw.get('token','')}-{raw.get('timestamp','')}"


def _provider_for(finding: dict) -> str:
    """Pick a human-readable provider label per finding for dedup keying."""
    ftype = finding.get("type", "")
    # Legacy categories
    if ftype == "browser":
        return finding.get("domain", "browser")
    if ftype == "package":
        return f"{finding.get('manager','pkg')}:{finding.get('name','')}"
    if ftype == "process":
        return finding.get("name", "process")
    if ftype == "ide_plugin":
        return finding.get("plugin_id", "ide_plugin")
    if ftype == "container_image":
        return finding.get("image", "container_image")
    if ftype == "container_log_signal":
        return f"container:{finding.get('signal','log')}"
    if ftype == "shell_history":
        return f"shell:{(finding.get('command_hint','') or 'cmd')[:40]}"
    # Phase 1A categories
    if ftype == "mcp_server":
        return f"mcp:{finding.get('mcp_host','')}:{finding.get('server_name','')}"
    if ftype == "agent_workflow":
        return f"workflow:{finding.get('framework','')}:{finding.get('filename','')}"
    if ftype == "agent_scheduled":
        return f"sched:{finding.get('trigger','')}:{(finding.get('command_safe','') or finding.get('plist_name',''))[:40]}"
    if ftype == "tool_registration":
        return f"tools:{finding.get('repo_name','')}"
    if ftype == "vector_db":
        return f"vdb:{finding.get('kind','')}:{finding.get('name','')}"
    return ftype or "unknown"


def _name_field(f: dict) -> str:
    """Distinctive identifier for non-browser findings → goes into process_name."""
    return (f.get("name") or f.get("plugin_id") or f.get("image")
            or f.get("signal") or (f.get("command_hint", "") or "")[:140])


# Phase 1A field-copy logic split into agent_explode_fields.py to keep
# this file under the 150-LOC cap. See that module's docstring.
from .agent_explode_fields import copy_phase_1a_fields as _copy_phase_1a_fields


def explode_endpoint_findings(raw: dict, company: str, bind_identity) -> list:
    """
    Turn one ENDPOINT_SCAN payload into one flat event per finding.
    `bind_identity(event, raw)` is passed in to avoid a circular import
    with normalizer/agent.py.
    Returns [] for clean scans — pipeline drops the whole payload.
    """
    findings = raw.get("findings") or []
    if not findings:
        return []
    events: list = []
    sid = _scan_id(raw)
    for f in findings:
        ftype = f.get("type", "")
        event = empty_event("agent_endpoint_scan", company)
        bind_identity(event, raw)
        event["timestamp"] = raw.get("timestamp", event["timestamp"])
        event["outcome"]   = "ENDPOINT_FINDING"
        event["severity"]  = _FINDING_SEVERITY.get(ftype, "LOW")
        event["provider"]  = _provider_for(f)
        event["category"]  = ftype
        event["scan_id"]   = sid
        if ftype == "browser":
            event["dst_domain"]   = f.get("domain", "")
        else:
            event["process_name"] = _name_field(f)
        # Copy Phase 1A fields onto the event so dashboards render them
        # without parsing the `notes` blob. No-op for legacy categories.
        _copy_phase_1a_fields(event, f)
        # Pass through scan_kind so dashboard can split baseline vs recurring.
        event["scan_kind"] = raw.get("scan_kind", "recurring")
        event["notes"] = json.dumps({
            "scan_id": sid, "finding": f, "token": raw.get("token", ""),
        })
        events.append(event)
    log.debug(f"ENDPOINT_SCAN exploded into {len(events)} events "
              f"from {raw.get('device_id','?')}")
    return events
