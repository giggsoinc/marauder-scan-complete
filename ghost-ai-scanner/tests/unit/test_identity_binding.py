# =============================================================
# FILE: tests/unit/test_identity_binding.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the Step 0 identity contract.
#          Every agent payload must carry email, device_uuid,
#          mac_primary, ip_set onto the flat event surfaced by
#          src/normalizer/agent.py — both for HEARTBEAT and
#          ENDPOINT_SCAN. Pure-data; no AWS, no LocalStack.
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Step 0.
# =============================================================

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from normalizer import agent as agent_normalizer  # noqa: E402


_RAW_HEARTBEAT = {
    "event_type":   "HEARTBEAT",
    "status":       "installed",
    "device_id":    "alice-mbp",
    "device_uuid":  "11111111-2222-3333-4444-555555555555",
    "mac_primary":  "aa:bb:cc:dd:ee:ff",
    "ip_set":       ["10.0.0.7", "192.168.1.42"],
    "email":        "alice@acme.com",
    "token":        "abc-123",
    "company":      "acme",
    "os_name":      "Darwin",
    "os_version":   "23.5.0",
    "agent_version":"2.0.0",
    "timestamp":    "2026-04-25T12:00:00+00:00",
}


_RAW_SCAN = {
    "event_type":   "ENDPOINT_SCAN",
    "device_id":    "alice-mbp",
    "device_uuid":  "11111111-2222-3333-4444-555555555555",
    "mac_primary":  "aa:bb:cc:dd:ee:ff",
    "ip_set":       ["10.0.0.7"],
    "email":        "alice@acme.com",
    "token":        "abc-123",
    "company":      "acme",
    "os_name":      "darwin",
    "timestamp":    "2026-04-25T12:00:00+00:00",
    "findings": [
        {"type": "package", "manager": "pip", "name": "langchain"},
        {"type": "browser", "browser": "chrome", "domain": "chatgpt.com", "visits": 4},
    ],
    "summary":  {"packages": 1, "browser_hits": 1},
}


def _expect_identity(event: dict, raw: dict) -> None:
    """Assert the four identity fields propagated."""
    assert event["mac_address"]  == raw["mac_primary"]
    assert event["device_uuid"]  == raw["device_uuid"]
    assert event["email"]        == raw["email"]
    assert event["ip_set"]       == raw["ip_set"]
    assert event["src_hostname"] == raw["device_id"]
    # owner = email per the Step 0 binding (was hostname before)
    assert event["owner"]        == raw["email"]


def test_heartbeat_carries_full_identity():
    event = agent_normalizer.parse(_RAW_HEARTBEAT, company="acme")
    _expect_identity(event, _RAW_HEARTBEAT)
    assert event["outcome"]    == "HEARTBEAT"
    assert event["asset_type"] == "laptop"


def test_endpoint_scan_carries_full_identity():
    event = agent_normalizer.parse(_RAW_SCAN, company="acme")
    _expect_identity(event, _RAW_SCAN)
    assert event["outcome"]  == "ALERT"           # had findings
    assert event["severity"] in ("HIGH", "MEDIUM", "LOW")


def test_severity_high_when_browser_finding_present():
    event = agent_normalizer.parse(_RAW_SCAN, company="acme")
    assert event["severity"] == "HIGH"


def test_severity_medium_when_only_packages():
    raw = {**_RAW_SCAN, "findings": [{"type": "package", "name": "langchain"}]}
    event = agent_normalizer.parse(raw, company="acme")
    assert event["severity"] == "MEDIUM"


def test_severity_low_when_only_shell_history():
    raw = {**_RAW_SCAN, "findings": [{"type": "shell_history", "shell": ".zsh_history",
                                      "command_hint": "docker run flowiseai/flowise"}]}
    event = agent_normalizer.parse(raw, company="acme")
    assert event["severity"] == "LOW"


def test_src_ip_falls_back_to_hostname_when_ip_set_empty():
    raw = {**_RAW_HEARTBEAT, "ip_set": []}
    event = agent_normalizer.parse(raw, company="acme")
    assert event["src_ip"] == raw["device_id"]


def test_src_ip_uses_first_ip_when_present():
    event = agent_normalizer.parse(_RAW_HEARTBEAT, company="acme")
    assert event["src_ip"] == "10.0.0.7"


def test_owner_falls_back_to_hostname_when_email_missing():
    raw = {**_RAW_HEARTBEAT, "email": ""}
    event = agent_normalizer.parse(raw, company="acme")
    assert event["owner"] == raw["device_id"]


def test_unknown_event_type_returns_none():
    assert agent_normalizer.parse({"event_type": "GIBBERISH"}, company="acme") is None
