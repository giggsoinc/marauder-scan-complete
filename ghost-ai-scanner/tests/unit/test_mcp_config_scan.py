# =============================================================
# FILE: tests/unit/test_mcp_config_scan.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.1
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the MCP-config scanner's contract:
#          - parses JSON shaped like Claude Desktop's config
#          - emits one finding per server
#          - drops arg VALUES (only flags survive)
#          - drops env values (only keys survive)
#          - hashes the file for change detection
#          - silently skips invalid JSON
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
#   v1.0.1  2026-04-26  Helper now runs the scanner inside the patched
#                       Path.home() scope (was being undone too early).
# =============================================================

import json
import os
import re
from pathlib import Path

REPO  = Path(__file__).resolve().parents[2]
FRAGS = REPO / "agent" / "install"


def _run_mcp_scan(home: Path) -> list:
    """Exec redactor + mcp scanner under fake $HOME and return findings.
    Path.home() patch persists for the entire scanner call so the
    fragment's module-level _HOME_RE and per-OS path table both
    resolve relative to the test home, not the real home."""
    ns: dict = {
        "re": re, "Path": Path, "os": os, "json": json,
        "subprocess": None,
        "OS_NAME": "darwin",
        "AGENT_DIR": home / ".patronai",
    }
    real_home = Path.home
    Path.home = staticmethod(lambda: home)                       # type: ignore
    try:
        for frag in ("scan_redactor.py.frag", "scan_mcp_configs.py.frag"):
            exec(compile((FRAGS / frag).read_text(), frag, "exec"), ns)
        return ns["scan_mcp_configs"]()
    finally:
        Path.home = real_home                                    # type: ignore


def _write_claude_desktop(home: Path, payload: dict) -> Path:
    """Drop a synthetic claude_desktop_config.json under the test home."""
    p = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_no_configs_means_no_findings(tmp_path):
    assert _run_mcp_scan(tmp_path) == []


def test_one_server_becomes_one_finding(tmp_path):
    _write_claude_desktop(tmp_path, {
        "mcpServers": {
            "filesystem": {
                "command": "/usr/local/bin/npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem",
                         "/Users/alice/projects"],
                "env": {"ALLOWED_DIRECTORIES": "/Users/alice/projects"},
            }
        }
    })
    out = _run_mcp_scan(tmp_path)
    assert len(out) == 1
    f = out[0]
    assert f["type"]             == "mcp_server"
    assert f["mcp_host"]         == "claude_desktop"
    assert f["server_name"]      == "filesystem"
    assert f["command_basename"] == "npx"


def test_arg_values_are_dropped(tmp_path):
    """Only `-` flags survive the arg filter; absolute paths must be gone."""
    _write_claude_desktop(tmp_path, {
        "mcpServers": {
            "fs": {
                "command": "node",
                "args": ["-y", "/Users/alice/.../leaky-server.js", "--port", "3000"],
            }
        }
    })
    f = _run_mcp_scan(tmp_path)[0]
    for a in f["arg_flags"]:
        assert a.startswith("-")
    assert "/Users/alice" not in str(f)


def test_env_values_are_dropped_keys_kept(tmp_path):
    _write_claude_desktop(tmp_path, {
        "mcpServers": {
            "x": {"command": "node", "args": [],
                  "env": {"OPENAI_API_KEY": "sk-1234567890abcdefghijABCDEFGHIJ"}}
        }
    })
    out = _run_mcp_scan(tmp_path)
    assert out, "expected one finding"
    f = out[0]
    assert "OPENAI_API_KEY" in f["env_keys_present"]
    assert "sk-1234567890abcdefghij" not in str(f)


def test_hash_changes_when_config_edits(tmp_path):
    p = _write_claude_desktop(tmp_path, {
        "mcpServers": {"a": {"command": "node", "args": []}}
    })
    h1 = _run_mcp_scan(tmp_path)[0]["config_sha256"]
    p.write_text(json.dumps({
        "mcpServers": {"a": {"command": "python", "args": []}}
    }))
    h2 = _run_mcp_scan(tmp_path)[0]["config_sha256"]
    assert h1 and h2 and h1 != h2


def test_invalid_json_is_skipped_quietly(tmp_path):
    p = tmp_path / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{this is not json", encoding="utf-8")
    assert _run_mcp_scan(tmp_path) == []


def test_mcp_scanner_under_loc_cap():
    body = (FRAGS / "scan_mcp_configs.py.frag").read_text()
    assert len(body.splitlines()) <= 150
