# =============================================================
# FILE: tests/unit/test_endpoint_scan_flow.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the Step 0.5 contract that fixes the empty dashboard:
#          - explode_endpoint_findings turns N findings into N events
#          - Clean scans drop entirely (no rows written)
#          - Each event tagged with scan_id + identity bundle
#          - Severity tier per finding type drives alerter routing
#          Pure-data; no AWS, no LocalStack.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Step 0.5.
# =============================================================

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from normalizer.agent import explode_endpoint_findings  # noqa: E402


_RAW_TEMPLATE = {
    "event_type":   "ENDPOINT_SCAN",
    "device_id":    "alice-mbp",
    "device_uuid":  "11111111-2222-3333-4444-555555555555",
    "mac_primary":  "aa:bb:cc:dd:ee:ff",
    "ip_set":       ["10.0.0.7", "192.168.1.42"],
    "email":        "alice@acme.com",
    "token":        "tok-abc",
    "company":      "acme",
    "timestamp":    "2026-04-26T12:00:00+00:00",
}


def _raw(*findings):
    return {**_RAW_TEMPLATE, "findings": list(findings),
            "summary": {"findings_count": len(findings)}}


def test_clean_scan_returns_empty_list():
    """Zero findings → drop entirely; heartbeat covers liveness."""
    events = explode_endpoint_findings(_raw(), company="acme")
    assert events == []


def test_one_finding_becomes_one_event():
    raw = _raw({"type": "package", "manager": "pip", "name": "langchain"})
    events = explode_endpoint_findings(raw, company="acme")
    assert len(events) == 1


def test_three_findings_become_three_events():
    raw = _raw(
        {"type": "browser", "browser": "chrome", "domain": "chatgpt.com", "visits": 4},
        {"type": "ide_plugin", "ide": "vscode", "plugin_id": "github.copilot"},
        {"type": "container_image", "name": "n8n", "image": "n8nio/n8n:latest"},
    )
    events = explode_endpoint_findings(raw, company="acme")
    assert len(events) == 3


def test_browser_finding_sets_dst_domain():
    raw = _raw({"type": "browser", "domain": "chatgpt.com", "browser": "chrome", "visits": 4})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["dst_domain"] == "chatgpt.com"
    assert e["category"]   == "browser"
    assert e["severity"]   == "HIGH"


def test_package_finding_sets_process_name():
    raw = _raw({"type": "package", "manager": "pip", "name": "langchain"})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["process_name"] == "langchain"
    assert e["severity"]     == "MEDIUM"
    assert e["provider"]     == "pip:langchain"


def test_ide_plugin_finding_sets_process_name():
    raw = _raw({"type": "ide_plugin", "ide": "vscode", "plugin_id": "github.copilot"})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["process_name"] == "github.copilot"
    assert e["severity"]     == "MEDIUM"


def test_severity_tiers_correct():
    cases = [
        ("browser",              {"domain": "x.com"},                 "HIGH"),
        ("process",              {"name": "ollama"},                  "HIGH"),
        ("container_log_signal", {"signal": "loading model"},         "HIGH"),
        ("package",              {"manager": "pip", "name": "lc"},    "MEDIUM"),
        ("ide_plugin",           {"plugin_id": "github.copilot"},     "MEDIUM"),
        ("container_image",      {"image": "x", "name": "x"},         "MEDIUM"),
        ("shell_history",        {"command_hint": "docker pull"},     "LOW"),
    ]
    for ftype, extra, expected in cases:
        finding = {"type": ftype, **extra}
        e = explode_endpoint_findings(_raw(finding), "acme")[0]
        assert e["severity"] == expected, f"{ftype} should be {expected}, got {e['severity']}"


def test_every_event_carries_identity_bundle():
    raw = _raw({"type": "package", "manager": "pip", "name": "langchain"})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["email"]        == _RAW_TEMPLATE["email"]
    assert e["device_uuid"]  == _RAW_TEMPLATE["device_uuid"]
    assert e["mac_address"]  == _RAW_TEMPLATE["mac_primary"]
    assert e["ip_set"]       == _RAW_TEMPLATE["ip_set"]
    assert e["src_hostname"] == _RAW_TEMPLATE["device_id"]
    assert e["asset_type"]   == "laptop"


def test_every_event_carries_scan_id():
    raw = _raw(
        {"type": "browser", "domain": "chatgpt.com"},
        {"type": "package", "manager": "pip", "name": "langchain"},
    )
    events = explode_endpoint_findings(raw, "acme")
    assert events[0]["scan_id"]
    assert events[0]["scan_id"] == events[1]["scan_id"]      # same scan
    assert _RAW_TEMPLATE["token"] in events[0]["scan_id"]


def test_outcome_is_endpoint_finding():
    raw = _raw({"type": "package", "manager": "pip", "name": "langchain"})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["outcome"] == "ENDPOINT_FINDING"


def test_unknown_finding_type_defaults_to_low():
    raw = _raw({"type": "future_type_we_havent_defined", "x": "y"})
    e = explode_endpoint_findings(raw, "acme")[0]
    assert e["severity"] == "LOW"


def test_notes_blob_contains_full_finding():
    """Notes JSON must hold the original finding so audit can replay."""
    import json
    finding = {"type": "package", "manager": "pip", "name": "langchain"}
    raw = _raw(finding)
    e = explode_endpoint_findings(raw, "acme")[0]
    notes = json.loads(e["notes"])
    assert notes["finding"] == finding
    assert notes["scan_id"] == e["scan_id"]
    assert notes["token"]   == _RAW_TEMPLATE["token"]
