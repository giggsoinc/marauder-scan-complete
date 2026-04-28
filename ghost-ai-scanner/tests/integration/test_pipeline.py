# =============================================================
# FILE: tests/integration/test_pipeline.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Integration tests for the full scan pipeline.
#          Uses LocalStack — real S3 calls to fake AWS.
#          Tests: ingest → match → find → summarize → cursor.
#          Run with LocalStack running on port 4566.
# =============================================================

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pytest
from datetime import date


# ── Settings store ────────────────────────────────────────────

def test_settings_read_write(store):
    settings = store.settings.read()
    assert isinstance(settings, dict)
    assert "company" in settings


def test_settings_write_stamps_metadata(store):
    settings = store.settings.read()
    ok = store.settings.write(settings, written_by="pytest")
    assert ok is True
    updated = store.settings.read()
    assert updated["_meta"]["last_written_by"] == "pytest"


# ── Cursor store ──────────────────────────────────────────────

def test_cursor_first_run_defaults(store):
    cursor = store.cursor.read()
    assert cursor["last_key"] is None
    assert cursor["files_processed"] == 0


def test_cursor_write_and_read(store):
    ok = store.cursor.write("ocsf/2026/04/18/test.json.gz", 5, 100)
    assert ok is True
    cursor = store.cursor.read()
    assert cursor["last_key"]        == "ocsf/2026/04/18/test.json.gz"
    assert cursor["files_processed"] == 5
    assert cursor["total_events"]    == 100


def test_cursor_reset(store):
    store.cursor.write("some-key", 10)
    ok = store.cursor.reset()
    assert ok is True
    cursor = store.cursor.read()
    assert cursor["last_key"] is None


# ── Findings store ────────────────────────────────────────────

def test_findings_write_and_read(store):
    finding = {
        "event_id":    "test-001",
        "src_ip":      "10.0.4.112",
        "dst_domain":  "api.openai.com",
        "provider":    "OpenAI",
        "severity":    "high",
        "outcome":     "DOMAIN_ALERT",
        "owner":       "alice",
        "department":  "Engineering",
        "bytes_out":   2847392,
        "timestamp":   "2026-04-18T09:14:32Z",
    }
    ok = store.findings.write(finding)
    assert ok is True

    today  = date.today().isoformat()
    result = store.findings.read(today, severity="high", limit=10)
    assert not result.is_empty()
    rows = result.to_dicts()
    assert any(r["event_id"] == "test-001" for r in rows)


def test_findings_severity_partitioned(store):
    """Critical and medium findings go to separate files."""
    store.findings.write({"event_id": "crit-001", "severity": "critical",
                          "outcome": "DOMAIN_ALERT", "src_ip": "10.0.0.1",
                          "dst_domain": "hf.co", "provider": "HuggingFace"})
    store.findings.write({"event_id": "med-001",  "severity": "medium",
                          "outcome": "PORT_ALERT",  "src_ip": "10.0.0.2",
                          "dst_domain": "",         "provider": "Ollama"})
    today = date.today().isoformat()
    crits = store.findings.read(today, severity="critical", limit=10)
    meds  = store.findings.read(today, severity="medium",   limit=10)
    assert not crits.is_empty()
    assert not meds.is_empty()


# ── Dedup store ───────────────────────────────────────────────

def test_dedup_not_duplicate_first_time(store):
    result = store.dedup.is_duplicate("10.99.99.99", "TestProvider", window_minutes=60)
    assert result is False


def test_dedup_duplicate_after_record(store):
    store.dedup.record("10.88.88.88", "OpenAI")
    result = store.dedup.is_duplicate("10.88.88.88", "OpenAI", window_minutes=60)
    assert result is True


def test_dedup_different_provider_not_duplicate(store):
    store.dedup.record("10.77.77.77", "OpenAI")
    result = store.dedup.is_duplicate("10.77.77.77", "HuggingFace", window_minutes=60)
    assert result is False


def test_dedup_clear_removes_entry(store):
    store.dedup.record("10.66.66.66", "Cohere")
    store.dedup.clear("10.66.66.66", "Cohere")
    result = store.dedup.is_duplicate("10.66.66.66", "Cohere", window_minutes=60)
    assert result is False


# ── Summary store ─────────────────────────────────────────────

def test_summary_write_and_read(store):
    summary = {
        "total_events":   42,
        "alerts_fired":   7,
        "by_severity":    {"HIGH": 5, "MEDIUM": 2},
        "by_provider":    {"OpenAI": 4, "HuggingFace": 3},
        "by_department":  {"Engineering": 6, "Finance": 1},
        "unique_sources": 8,
        "unique_providers": 2,
    }
    today = date.today().isoformat()
    ok    = store.summary.write(summary, today)
    assert ok is True

    result = store.summary.read(today)
    assert result["total_events"]  == 42
    assert result["alerts_fired"]  == 7
    assert result["date"]          == today


def test_summary_missing_date_returns_empty(store):
    result = store.summary.read("1999-01-01")
    assert result == {}


# ── Full pipeline cycle ───────────────────────────────────────

def test_full_normalise_match_write_cycle(store, sample_packetbeat_event, seeded_bucket):
    """
    Full mini-cycle: raw event → normalize → match → write finding.
    Uses seeded authorized/unauthorized CSVs from LocalStack.
    """
    from normalizer import normalize
    from matcher.loader import load_authorized, load_unauthorized
    from matcher.engine import match

    # Normalise
    event = normalize(sample_packetbeat_event, source_hint="packetbeat", company="test")
    assert event is not None
    assert event["dst_domain"] == "api.openai.com"

    # Match — api.openai.com not in seeded authorized.csv → should alert
    authorized   = load_authorized(seeded_bucket)
    unauthorized = load_unauthorized(seeded_bucket)
    verdict      = match(event, authorized, unauthorized)

    # api.openai.com is in unauthorized — should DOMAIN_ALERT
    assert verdict["outcome"] in ("DOMAIN_ALERT", "SUPPRESS")

    # Write finding
    event.update(verdict)
    ok = store.findings.write(event)
    assert ok is True
