# =============================================================
# FILE: tests/unit/test_pipeline_mcp_change.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the MCP-config-change detection contract:
#          - Non-MCP findings: no derived event, no hash recorded
#          - First-ever MCP sighting: no derived event (no last hash to flip)
#                                     but hash IS recorded for next time
#          - Subsequent same-hash: no derived event
#          - Hash flip: derived event with HIGH severity + MCP_CONFIG_CHANGED
#                       outcome + provider tag, hash updated
#          Mock-based; no real S3.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))


def _make_store(last_hash: str = ""):
    """Build a fake store with .findings.s3 + .findings.bucket attrs.
    last_known_mcp_hash returns `last_hash`. Tracks write calls."""
    findings = MagicMock()
    findings.s3      = MagicMock()
    findings.bucket  = "test-bucket"
    findings.write   = MagicMock(return_value=True)
    store = MagicMock()
    store.findings   = findings
    return store, findings


def _mcp_event(hash_value: str = "abc123") -> dict:
    return {
        "category":      "mcp_server",
        "src_hostname":  "alice-mbp",
        "email":         "alice@acme.com",
        "mcp_host":      "claude_desktop",
        "config_sha256": hash_value,
        "severity":      "HIGH",
        "provider":      "mcp:claude_desktop:filesystem",
    }


def test_non_mcp_event_is_ignored():
    """Non-MCP categories must not trigger any hash logic."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    event = {"category": "package", "src_hostname": "x"}
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash") as lk, \
         patch("ingestor.pipeline_mcp_change.record_mcp_hash") as rec:
        maybe_emit_mcp_change(store, event)
    lk.assert_not_called()
    rec.assert_not_called()
    findings.write.assert_not_called()


def test_first_sighting_records_but_does_not_emit_change():
    """No prior hash → record current hash, but no derived event written."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash",
               return_value="") as lk, \
         patch("ingestor.pipeline_mcp_change.record_mcp_hash") as rec:
        maybe_emit_mcp_change(store, _mcp_event("abc123"))
    lk.assert_called_once()
    rec.assert_called_once()
    findings.write.assert_not_called()      # no derived change event


def test_unchanged_hash_does_not_emit_change():
    """Same hash as last → no derived event; record stays a no-op write."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash",
               return_value="abc123"), \
         patch("ingestor.pipeline_mcp_change.record_mcp_hash"):
        maybe_emit_mcp_change(store, _mcp_event("abc123"))
    findings.write.assert_not_called()


def test_hash_flip_emits_change_event():
    """Different hash → derived MCP_CONFIG_CHANGED event MUST be written."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash",
               return_value="OLDHASH"), \
         patch("ingestor.pipeline_mcp_change.record_mcp_hash"):
        maybe_emit_mcp_change(store, _mcp_event("NEWHASH"))
    findings.write.assert_called_once()
    written = findings.write.call_args[0][0]
    assert written["category"] == "mcp_config_changed"
    assert written["outcome"]  == "MCP_CONFIG_CHANGED"
    assert written["severity"] == "HIGH"
    assert "OLDHASH"[:8] in written["notes"]
    assert "NEWHASH"[:8] in written["notes"]


def test_missing_device_or_host_is_skipped():
    """Without device + mcp_host + new_hash, change detection bails cleanly."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    bad = {"category": "mcp_server", "src_hostname": "", "mcp_host": "", "config_sha256": ""}
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash") as lk:
        maybe_emit_mcp_change(store, bad)
    lk.assert_not_called()
    findings.write.assert_not_called()


def test_provider_tag_marks_derived_event():
    """The derived event's `provider` is `mcp-change:<host>` so dedup
    keys it separately from the base MCP-server event."""
    from ingestor.pipeline_mcp_change import maybe_emit_mcp_change

    store, findings = _make_store()
    with patch("ingestor.pipeline_mcp_change.last_known_mcp_hash",
               return_value="OLDHASH"), \
         patch("ingestor.pipeline_mcp_change.record_mcp_hash"):
        maybe_emit_mcp_change(store, _mcp_event("NEWHASH"))
    written = findings.write.call_args[0][0]
    assert written["provider"] == "mcp-change:claude_desktop"
