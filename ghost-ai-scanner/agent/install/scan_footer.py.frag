# =============================================================
# FRAGMENT: scan_footer.py.frag
# VERSION: 2.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Bottom of the rendered scan.sh Python block.
#          Calls every scan_*() function defined by sibling fragments,
#          aggregates findings into a single ENDPOINT_SCAN payload,
#          and prints the JSON to stdout. The bash wrapper PUTs it to S3.
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 2 — fragment refactor.
#   v2.0.0  2026-04-26  Phase 1A. Calls 4 new emitters (mcp_configs,
#                       agents_workflows, tools_code, vector_dbs).
#                       Adds scan_kind tag (`baseline` first run, then
#                       `recurring`). Clears first_run flag once the
#                       payload is built. Adds repo discovery summary.
# =============================================================

_findings: list = []
# --- legacy emitters ---
_findings += scan_packages()
_findings += scan_processes()
_findings += scan_browsers()
_findings += scan_ide_plugins()
_findings += scan_containers()
_findings += scan_shell_history()
# --- Phase 1A new emitters ---
_findings += scan_mcp_configs()
_findings += scan_agents_workflows()
_findings += scan_tools_code()
_findings += scan_vector_dbs()


def _count(kind: str) -> int:
    """Count findings of a given type for the summary block."""
    return sum(1 for f in _findings if f.get("type") == kind)


_scan_kind = "baseline" if IS_FIRST_RUN else "recurring"

_payload = {
    "event_type":   "ENDPOINT_SCAN",
    "source":       "patronai_scan_agent",
    "device_id":    DEVICE_ID,
    "device_uuid":  DEVICE_UUID,
    "mac_primary":  MAC_PRIMARY,
    "ip_set":       IP_SET,
    "email":        EMAIL,
    "token":        TOKEN,
    "company":      COMPANY,
    "os_name":      OS_NAME,
    "timestamp":    NOW,
    "scan_kind":    _scan_kind,
    "authorized":   AUTH_LIST,
    "repos_discovered": [{"name": r.get("name"),
                          "remote_host": r.get("remote_host"),
                          "head_sha": r.get("head_sha"),
                          "path_safe": r.get("path_safe")}
                         for r in DISCOVERED_REPOS],
    "findings":     _findings,
    "summary": {
        "packages":              _count("package"),
        "processes":             _count("process"),
        "browser_hits":          _count("browser"),
        "ide_plugins":           _count("ide_plugin"),
        "container_images":      _count("container_image"),
        "container_log_signals": _count("container_log_signal"),
        "shell_history":         _count("shell_history"),
        "mcp_servers":           _count("mcp_server"),
        "agent_workflows":       _count("agent_workflow"),
        "agent_scheduled":       _count("agent_scheduled"),
        "tool_registrations":    _count("tool_registration"),
        "vector_dbs":            _count("vector_db"),
        "repos_discovered":      len(DISCOVERED_REPOS),
    },
}

# Drop the first-run flag now that a complete payload is ready.
# Best-effort — never block a scan on a flag-clearing failure.
try:
    _clear_first_run_flag()
except Exception:
    pass

print(json.dumps(_payload))
