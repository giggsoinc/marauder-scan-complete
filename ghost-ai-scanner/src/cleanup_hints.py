# =============================================================
# FILE: src/cleanup_hints.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Per-category cleanup-suggestion mapping.
#          Returns a HUMAN-READABLE hint operators can copy-paste to
#          remove an AI tool from a device. The agent NEVER executes
#          these — that's a deliberate security boundary. The hint is
#          rendered next to the finding so the operator can decide.
# DEPENDS: (stdlib only)
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

# Hint resolved from (category, os_name) → string. None means "no
# automatic suggestion — operator's call." OS is best-effort; falls
# back to a cross-platform hint when device OS is unknown.
_HINTS = {
    "process": {
        "darwin":  "Quit the app + remove from /Applications/. "
                   "macOS Login Items: System Settings → General → Login Items.",
        "linux":   "killall <process>; check ~/.config/autostart/ and "
                   "systemd --user list-unit-files for restart triggers.",
        "windows": "Task Manager → End task; remove from Startup tab.",
        "*":       "Stop the running process and remove from auto-start.",
    },
    "package": {
        "*": "Uninstall from the relevant package manager: "
             "pip uninstall <name>  |  npm uninstall -g <name>  |  "
             "brew uninstall <name>",
    },
    "ide_plugin": {
        "*": "VS Code/Cursor: code --uninstall-extension <plugin_id>. "
             "JetBrains: Preferences → Plugins → Uninstall.",
    },
    "mcp_server": {
        "darwin":  "Edit ~/Library/Application Support/Claude/"
                   "claude_desktop_config.json — remove the entry under "
                   "`mcpServers`. Restart Claude Desktop.",
        "windows": "Edit %APPDATA%\\Claude\\claude_desktop_config.json — "
                   "remove the entry. Restart Claude Desktop.",
        "linux":   "Edit ~/.config/Claude/claude_desktop_config.json — "
                   "remove the entry. Restart Claude Desktop.",
        "*":       "Remove the entry from your MCP host config and "
                   "restart the host (Claude Desktop / Cursor / Continue).",
    },
    "agent_workflow": {
        "*": "Delete or move the workflow file out of the watched path "
             "(or stop the orchestrator: e.g. `pm2 stop flowise`).",
    },
    "agent_scheduled": {
        "darwin":  "launchctl unload ~/Library/LaunchAgents/<plist>; "
                   "rm ~/Library/LaunchAgents/<plist>",
        "linux":   "crontab -e and remove the line, or "
                   "systemctl --user disable <unit>.",
        "windows": "schtasks /Delete /TN <task_name>",
        "*":       "Disable the cron/launchd/scheduled-task that "
                   "triggers this workflow.",
    },
    "vector_db": {
        "*": "Locate the file/folder via the `path_safe` field and "
             "`rm -rf <path>`. Sensitive: vector DBs can contain "
             "embeddings derived from your code/docs.",
    },
    "browser": {
        "*": "No on-device action — close the tab or block the domain "
             "via your proxy / browser extension allowlist.",
    },
    "container_image": {
        "*": "docker rmi <image>  (and stop any container running it).",
    },
    "container_log_signal": {
        "*": "Inspect the container; rotate any API key that leaked "
             "into logs.",
    },
    "shell_history": {
        "*": "Past command — usually informational. If it leaked a "
             "secret, rotate it.",
    },
    "tool_registration": {
        "*": "Code-level @tool decorator — review the repo and remove "
             "if not authorised.",
    },
}


def cleanup_hint(category: str, os_name: str = "") -> str:
    """Return a human-readable cleanup suggestion for a finding.
    `os_name` is optional — falls back to the cross-platform hint.
    Returns empty string when no hint is known."""
    cat = (category or "").lower()
    os_  = (os_name or "").lower()
    bucket = _HINTS.get(cat)
    if not bucket:
        return ""
    return bucket.get(os_) or bucket.get("*") or ""
