# =============================================================
# FILE: tests/unit/test_normalizer.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Unit tests for all normalizer parsers.
#          No AWS calls. Pure Python. Fast.
# =============================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from normalizer import normalize
from normalizer.schema import FLAT_SCHEMA


def test_all_schema_fields_present():
    """Every normalised event must have all flat schema fields."""
    raw   = {"@timestamp": "2026-04-18T09:00:00Z",
             "source": {"ip": "10.0.0.1", "bytes": 100},
             "destination": {"ip": "1.2.3.4", "port": 443, "domain": "api.openai.com"},
             "network": {"transport": "tcp"}}
    event = normalize(raw, source_hint="packetbeat", company="test")
    assert event is not None
    for field in FLAT_SCHEMA:
        assert field in event, f"Missing field: {field}"


def test_packetbeat_domain_extracted(sample_packetbeat_event):
    event = normalize(sample_packetbeat_event, source_hint="packetbeat", company="test")
    assert event is not None
    assert event["dst_domain"] == "api.openai.com"
    assert event["src_ip"]     == "10.0.4.112"
    assert event["bytes_out"]  == 2847392
    assert event["process_name"] == "python3"
    assert event["source"]     == "packetbeat"


def test_flow_log_accepted_only(sample_flow_log_line):
    event = normalize(sample_flow_log_line, source_hint="vpc_flow", company="test")
    assert event is not None
    assert event["src_ip"]   == "10.0.4.112"
    assert event["dst_port"] == 443
    assert event["source"]   == "vpc_flow"


def test_flow_log_reject_skipped():
    """REJECT actions must be dropped — already blocked by firewall."""
    line  = "2 123 eni-x 10.0.0.1 1.2.3.4 123 443 6 1 100 1000 1060 REJECT OK"
    event = normalize(line, source_hint="vpc_flow")
    assert event is None


def test_nac_row_identity_fields():
    raw   = {"IP Address": "192.168.1.10", "MAC Address": "AA:BB:CC:DD:EE:FF",
             "Username/Device": "alice", "Location": "HQ"}
    event = normalize(raw, source_hint="nac_csv", company="test")
    assert event is not None
    assert event["src_ip"]      == "192.168.1.10"
    assert event["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert event["owner"]       == "alice"
    assert event["source"]      == "nac_csv"


def test_agent_code_signal(sample_code_signal):
    event = normalize(sample_code_signal, source_hint="agent", company="test")
    assert event is not None
    assert event["source"]       == "agent_fs_watcher"
    assert "autogen" in event["code_snippet"].lower()
    assert event["file_path"]    == "/home/dev/project/agent.py"


def test_agent_git_diff(sample_git_diff):
    event = normalize(sample_git_diff, source_hint="agent", company="test")
    assert event is not None
    assert event["source"]   == "agent_git_hook"
    assert event["repo"]     == "ai-project"
    assert "crewai" in event["git_diff"].lower()


def test_auto_detect_packetbeat(sample_packetbeat_event):
    """Auto-detection without source_hint."""
    event = normalize(sample_packetbeat_event, company="test")
    assert event is not None
    assert event["source"] == "packetbeat"


def test_auto_detect_flow_log(sample_flow_log_line):
    event = normalize(sample_flow_log_line, company="test")
    assert event is not None
    assert event["source"] == "vpc_flow"


def test_none_returned_for_empty():
    assert normalize({}) is None
    assert normalize("") is None
