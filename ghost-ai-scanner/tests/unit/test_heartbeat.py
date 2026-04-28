# =============================================================
# FILE: tests/unit/test_heartbeat.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Unit tests for heartbeat ingestion path.
#          Covers: normaliser parsing, pipeline bypass, presigned URL TTL.
#          No AWS calls — all external dependencies mocked.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — Fix B heartbeat tests
# =============================================================

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from normalizer.agent import parse as agent_parse
from ingestor.pipeline import Pipeline


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def heartbeat_raw() -> dict:
    """Minimal HEARTBEAT payload from an edge agent."""
    return {
        "event_type":      "HEARTBEAT",
        "device_id":       "laptop-ravi",
        "owner":           "ravi@corp.com",
        "os_name":         "Darwin",
        "os_version":      "24.4.0",
        "agent_version":   "1.0.0",
        "uptime_seconds":  3600,
        "token":           "tok-abc-123",
        "timestamp":       "2026-04-19T10:00:00Z",
    }


@pytest.fixture
def mock_store() -> MagicMock:
    """Pipeline store stub — tracks write calls."""
    store = MagicMock()
    store.findings.write = MagicMock()
    return store


# ── Normaliser ────────────────────────────────────────────────

def test_heartbeat_outcome_is_heartbeat(heartbeat_raw: dict) -> None:
    """agent_parse must set outcome=HEARTBEAT for HEARTBEAT event type."""
    event = agent_parse(heartbeat_raw, company="test")
    assert event is not None
    assert event["outcome"] == "HEARTBEAT"


def test_heartbeat_severity_clean(heartbeat_raw: dict) -> None:
    """HEARTBEAT events must carry severity=CLEAN (not UNKNOWN)."""
    event = agent_parse(heartbeat_raw, company="test")
    assert event is not None
    assert event["severity"] == "CLEAN"


def test_heartbeat_source_is_agent_heartbeat(heartbeat_raw: dict) -> None:
    """source field must be 'agent_heartbeat'."""
    event = agent_parse(heartbeat_raw, company="test")
    assert event is not None
    assert event["source"] == "agent_heartbeat"


def test_heartbeat_device_id_in_src_ip(heartbeat_raw: dict) -> None:
    """device_id must map to src_ip and src_hostname."""
    event = agent_parse(heartbeat_raw, company="test")
    assert event is not None
    assert event["src_ip"]       == "laptop-ravi"
    assert event["src_hostname"] == "laptop-ravi"


def test_heartbeat_notes_contains_token(heartbeat_raw: dict) -> None:
    """notes JSON must include the agent token for status reconciliation."""
    event = agent_parse(heartbeat_raw, company="test")
    assert event is not None
    notes = json.loads(event["notes"])
    assert notes["token"]         == "tok-abc-123"
    assert notes["agent_version"] == "1.0.0"
    assert notes["os_name"]       == "Darwin"


def test_heartbeat_unknown_event_type_returns_none() -> None:
    """Unrecognised event_type must return None (no partial event)."""
    result = agent_parse({"event_type": "MYSTERY"}, company="test")
    assert result is None


# ── Pipeline bypass ───────────────────────────────────────────

def test_pipeline_heartbeat_writes_to_store(
    heartbeat_raw: dict,
    mock_store: MagicMock,
) -> None:
    """Pipeline must write HEARTBEAT event to findings store."""
    pipeline = Pipeline(mock_store, authorized=[], unauthorized=[], company="test")
    raw_event = {**heartbeat_raw, "_hint": "agent"}

    outcome = pipeline.process(raw_event)

    assert outcome == "HEARTBEAT"
    mock_store.findings.write.assert_called_once()


def test_pipeline_heartbeat_skips_match_step(
    heartbeat_raw: dict,
    mock_store: MagicMock,
) -> None:
    """Pipeline must NOT call match() for HEARTBEAT — bypass dst gate."""
    pipeline = Pipeline(mock_store, authorized=[], unauthorized=[], company="test")
    raw_event = {**heartbeat_raw, "_hint": "agent"}

    with patch("ingestor.pipeline.Pipeline.process",
               wraps=pipeline.process) as _wrapped:
        # Patch matcher.match to detect if it gets called
        with patch("matcher.match") as mock_match:
            pipeline.process(raw_event)
            mock_match.assert_not_called()


# ── Presigned URL TTL ─────────────────────────────────────────

def test_heartbeat_put_url_uses_7_day_ttl() -> None:
    """get_presigned_urls must generate heartbeat_put_url with 7-day TTL.

    Note: `MagicMock(spec=AgentStore)` auto-mocks every method on the
    spec, including the private signers. The original test only unbound
    `get_presigned_urls`, so the auto-mocked `_sign_put` / `_sign_get`
    intercepted the calls and `generate_presigned_url` never fired.
    Fix: also unbind the real signers so they reach the mocked s3.
    """
    from store.agent_store import AgentStore, HEARTBEAT_PRESIGN_TTL

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

    store = MagicMock(spec=AgentStore)
    store.s3     = mock_s3
    store.bucket = "test-bucket"
    store.get_presigned_urls = AgentStore.get_presigned_urls.__get__(store, AgentStore)
    store._sign_get          = AgentStore._sign_get.__get__(store, AgentStore)
    store._sign_put          = AgentStore._sign_put.__get__(store, AgentStore)

    store.get_presigned_urls("tok-123", "mac")

    # Collect all ExpiresIn values used across calls
    ttls = [
        call.kwargs.get("ExpiresIn", call.args[2] if len(call.args) > 2 else None)
        for call in mock_s3.generate_presigned_url.call_args_list
    ]
    assert HEARTBEAT_PRESIGN_TTL in ttls, (
        f"7-day TTL ({HEARTBEAT_PRESIGN_TTL}s) not found in presign calls: {ttls}"
    )
    assert HEARTBEAT_PRESIGN_TTL == 604800
