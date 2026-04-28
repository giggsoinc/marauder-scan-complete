# =============================================================
# FILE: tests/unit/test_agent_explode_phase1a.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the Phase 1A explode contract:
#          - 4 new categories get the correct severity tier
#          - _provider_for produces a meaningful dedup key per category
#          - whitelisted Phase 1A fields are PROMOTED onto the flat event
#            (so dashboards see them as columns, not buried in `notes`)
#          - scan_kind passes through from raw payload onto every event
#          Pure data; no AWS, no LocalStack.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from normalizer.agent           import explode_endpoint_findings   # noqa: E402
from normalizer.agent_explode_fields import (PHASE_1A_FIELD_MAP,    # noqa: E402
                                              copy_phase_1a_fields)


_RAW_TEMPLATE = {
    "event_type":   "ENDPOINT_SCAN",
    "device_id":    "alice-mbp",
    "device_uuid":  "uuid-1",
    "mac_primary":  "aa:bb:cc:dd:ee:ff",
    "ip_set":       ["10.0.0.7"],
    "email":        "alice@acme.com",
    "token":        "tok-abc",
    "company":      "acme",
    "timestamp":    "2026-04-26T12:00:00+00:00",
    "scan_kind":    "baseline",
}


def _raw(*findings):
    return {**_RAW_TEMPLATE, "findings": list(findings)}


# ── Severity tiers ─────────────────────────────────────────────

def test_mcp_server_is_high_severity():
    e = explode_endpoint_findings(
        _raw({"type": "mcp_server", "mcp_host": "claude_desktop",
              "server_name": "filesystem"}), "acme")[0]
    assert e["severity"] == "HIGH"


def test_agent_workflow_is_high_severity():
    e = explode_endpoint_findings(
        _raw({"type": "agent_workflow", "framework": "n8n",
              "filename": "flow.json"}), "acme")[0]
    assert e["severity"] == "HIGH"


def test_agent_scheduled_is_high_severity():
    e = explode_endpoint_findings(
        _raw({"type": "agent_scheduled", "trigger": "crontab",
              "command_safe": "python agent.py"}), "acme")[0]
    assert e["severity"] == "HIGH"


def test_tool_registration_is_medium_severity():
    e = explode_endpoint_findings(
        _raw({"type": "tool_registration", "repo_name": "rag",
              "total_tools": 3}), "acme")[0]
    assert e["severity"] == "MEDIUM"


def test_vector_db_is_medium_severity():
    e = explode_endpoint_findings(
        _raw({"type": "vector_db", "kind": "chroma", "name": "chroma.sqlite3"}),
        "acme")[0]
    assert e["severity"] == "MEDIUM"


# ── Provider strings (drive dedup keying) ──────────────────────

def test_mcp_provider_includes_host_and_server():
    e = explode_endpoint_findings(
        _raw({"type": "mcp_server", "mcp_host": "cursor",
              "server_name": "filesystem"}), "acme")[0]
    assert "cursor" in e["provider"] and "filesystem" in e["provider"]


def test_workflow_provider_includes_framework():
    e = explode_endpoint_findings(
        _raw({"type": "agent_workflow", "framework": "flowise",
              "filename": "agent.json"}), "acme")[0]
    assert "flowise" in e["provider"]


def test_vector_db_provider_includes_kind():
    e = explode_endpoint_findings(
        _raw({"type": "vector_db", "kind": "faiss", "name": "x.faiss"}),
        "acme")[0]
    assert "faiss" in e["provider"]


# ── Phase 1A field promotion (top-level columns on event) ───────

def test_mcp_fields_promoted_to_top_level():
    finding = {"type": "mcp_server", "mcp_host": "claude_desktop",
               "server_name": "filesystem", "command_basename": "npx",
               "config_sha256": "abc123def456",
               "arg_flags": ["-y"], "env_keys_present": ["OPENAI_API_KEY"],
               "transport": "stdio", "config_basename": "claude_desktop_config.json"}
    e = explode_endpoint_findings(_raw(finding), "acme")[0]
    assert e["mcp_host"]         == "claude_desktop"
    assert e["server_name"]      == "filesystem"
    assert e["command_basename"] == "npx"
    assert e["config_sha256"]    == "abc123def456"
    assert e["arg_flags"]        == ["-y"]
    assert e["env_keys_present"] == ["OPENAI_API_KEY"]
    assert e["transport"]        == "stdio"


def test_workflow_fields_promoted():
    finding = {"type": "agent_workflow", "framework": "n8n",
               "filename": "flow.json", "file_safe": "~/.n8n/flow.json",
               "bytes": 4096, "mtime_epoch": 1700000000}
    e = explode_endpoint_findings(_raw(finding), "acme")[0]
    assert e["framework"] == "n8n"
    assert e["filename"]  == "flow.json"
    assert e["bytes"]     == 4096


def test_vector_db_fields_promoted():
    finding = {"type": "vector_db", "kind": "chroma",
               "source": "home_cache", "path_safe": "~/.chroma/",
               "name": "chroma.sqlite3", "bytes": 1024}
    e = explode_endpoint_findings(_raw(finding), "acme")[0]
    assert e["kind"]      == "chroma"
    assert e["source"]    == "home_cache"
    assert e["path_safe"] == "~/.chroma/"


# ── scan_kind passthrough ──────────────────────────────────────

def test_scan_kind_propagates_baseline():
    raw = {**_RAW_TEMPLATE, "scan_kind": "baseline",
           "findings": [{"type": "vector_db", "kind": "faiss"}]}
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["scan_kind"] == "baseline"


def test_scan_kind_defaults_to_recurring_when_missing():
    raw = {**_RAW_TEMPLATE, "findings": [{"type": "vector_db", "kind": "faiss"}]}
    raw.pop("scan_kind", None)
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["scan_kind"] == "recurring"


# ── copy_phase_1a_fields helper directly ───────────────────────

def test_copy_phase_1a_is_noop_for_legacy_categories():
    event = {"type": "browser"}
    finding = {"type": "browser", "domain": "x.com", "anything": "leak?"}
    copy_phase_1a_fields(event, finding)
    # No fields outside the whitelist appear on the event.
    assert "anything" not in event


def test_copy_phase_1a_skips_missing_fields_quietly():
    event = {}
    copy_phase_1a_fields(event, {"type": "mcp_server"})        # nothing to copy
    assert event == {}                                          # no exception, no extra keys


def test_field_map_covers_all_new_categories():
    """Every category in agent_explode._FINDING_SEVERITY (Phase 1A row set)
    must have an entry in PHASE_1A_FIELD_MAP — else field promotion is lost."""
    expected = {"mcp_server", "agent_workflow", "agent_scheduled",
                "tool_registration", "vector_db"}
    assert expected.issubset(set(PHASE_1A_FIELD_MAP.keys()))
