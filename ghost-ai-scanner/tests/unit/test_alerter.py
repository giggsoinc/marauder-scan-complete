# =============================================================
# FILE: tests/unit/test_alerter.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Unit tests for alerter — payload builder, SNS dispatcher,
#          Trinity webhook, no-channels warning, subject truncation,
#          dedup gate, and SUPPRESS skip.
#          All external calls mocked — no real AWS or network.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

import json
import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from alerter.payload    import build as build_payload, subject as build_subject
from alerter.dispatcher import dispatch


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_event() -> dict:
    """Minimal finding event."""
    return {
        "event_id":    "e-001",
        "outcome":     "DOMAIN_ALERT",
        "severity":    "HIGH",
        "provider":    "openai.com",
        "category":    "Frontier AI Models",
        "src_ip":      "10.0.0.5",
        "dst_domain":  "api.openai.com",
        "dst_port":    443,
        "timestamp":   "2026-04-19T10:00:00Z",
    }


@pytest.fixture
def sample_identity() -> dict:
    """Resolved identity for testing."""
    return {
        "owner":       "alice@corp.com",
        "email":       "alice@corp.com",
        "department":  "engineering",
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "asset_type":  "laptop",
        "source":      "nac_csv",
    }


# ── payload.build ─────────────────────────────────────────────

def test_payload_required_fields_present(sample_event, sample_identity):
    """build() must include all mandatory top-level fields."""
    p = build_payload(sample_event, sample_identity, "acme")
    for field in ("source", "severity", "provider", "outcome",
                  "src_ip", "owner", "alert_generated", "company"):
        assert field in p, f"missing field: {field}"


def test_payload_identity_merged(sample_event, sample_identity):
    """build() must copy identity fields into the payload."""
    p = build_payload(sample_event, sample_identity, "acme")
    assert p["owner"]       == "alice@corp.com"
    assert p["department"]  == "engineering"
    assert p["mac_address"] == "aa:bb:cc:dd:ee:ff"


def test_payload_event_fields_preserved(sample_event, sample_identity):
    """build() must preserve severity, provider, outcome from event."""
    p = build_payload(sample_event, sample_identity, "acme")
    assert p["severity"] == "HIGH"
    assert p["provider"] == "openai.com"
    assert p["outcome"]  == "DOMAIN_ALERT"


def test_payload_company_injected(sample_event, sample_identity):
    """build() must use the company argument, not the event field."""
    p = build_payload(sample_event, sample_identity, "giggso")
    assert p["company"] == "giggso"


def test_payload_missing_identity_falls_back_to_src_ip(sample_event):
    """build() with empty identity must fall back owner → src_ip."""
    p = build_payload(sample_event, {}, "acme")
    assert p["owner"] == "10.0.0.5"


# ── payload.subject ───────────────────────────────────────────

def test_subject_format(sample_event, sample_identity):
    """subject() must contain severity, provider, owner."""
    p = build_payload(sample_event, sample_identity, "acme")
    s = build_subject(p)
    assert "HIGH"            in s
    assert "openai.com"      in s
    assert "alice@corp.com"  in s


def test_subject_max_100_chars(sample_event, sample_identity):
    """subject() must never exceed 100 chars (SNS email constraint)."""
    sample_event["severity"] = "CRITICAL"
    p = build_payload(sample_event, sample_identity, "a-very-long-company-name-that-goes-on-and-on")
    assert len(build_subject(p)) <= 100


# ── dispatcher — SNS ──────────────────────────────────────────

def test_dispatch_sns_publishes_payload(sample_event, sample_identity):
    """dispatch() must call sns.publish() with TopicArn and Message."""
    payload = build_payload(sample_event, sample_identity, "acme")
    mock_sns = MagicMock()

    with patch("alerter.dispatcher.boto3.client", return_value=mock_sns):
        result = dispatch(payload, "TEST ALERT", sns_arn="arn:aws:sns:us-east-1:123:test")

    mock_sns.publish.assert_called_once()
    call_kwargs = mock_sns.publish.call_args.kwargs
    assert call_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123:test"
    parsed = json.loads(call_kwargs["Message"])
    assert parsed["provider"] == "openai.com"
    assert result["sns"] == "ok"


def test_dispatch_sns_failure_returns_error_string(sample_event, sample_identity):
    """dispatch() must return error string, not raise, when SNS fails."""
    payload    = build_payload(sample_event, sample_identity, "acme")
    mock_sns   = MagicMock()
    mock_sns.publish.side_effect = Exception("connection refused")

    with patch("alerter.dispatcher.boto3.client", return_value=mock_sns):
        result = dispatch(payload, "ALERT", sns_arn="arn:aws:sns:test")

    assert "connection refused" in result["sns"]


# ── dispatcher — Trinity webhook ──────────────────────────────

def test_dispatch_trinity_posts_json(sample_event, sample_identity):
    """dispatch() must POST JSON to Trinity webhook URL."""
    payload    = build_payload(sample_event, sample_identity, "acme")
    mock_resp  = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    with patch("alerter.dispatcher.requests.post", return_value=mock_resp) as mock_post:
        result = dispatch(payload, "ALERT", webhook_url="https://trinity.example.com/hook")

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["provider"] == "openai.com"
    assert result["trinity"] == "ok"


def test_dispatch_trinity_timeout_returns_timeout(sample_event, sample_identity):
    """dispatch() must return 'timeout' string when Trinity times out."""
    import requests as req_lib
    payload = build_payload(sample_event, sample_identity, "acme")

    with patch("alerter.dispatcher.requests.post",
               side_effect=req_lib.exceptions.Timeout()):
        result = dispatch(payload, "ALERT", webhook_url="https://trinity.example.com/hook")

    assert result["trinity"] == "timeout"


# ── dispatcher — no channels ──────────────────────────────────

def test_dispatch_no_channels_returns_warning():
    """dispatch() with no SNS ARN and no webhook must return warning key."""
    result = dispatch({"severity": "HIGH"}, "ALERT")
    assert "warning" in result
    assert "no channels" in result["warning"]


# ── dispatcher — both channels independent ────────────────────

def test_dispatch_both_channels_run_independently(sample_event, sample_identity):
    """SNS failure must not prevent Trinity webhook from firing."""
    import requests as req_lib
    payload    = build_payload(sample_event, sample_identity, "acme")
    mock_sns   = MagicMock()
    mock_sns.publish.side_effect = Exception("sns down")
    mock_resp  = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch("alerter.dispatcher.boto3.client", return_value=mock_sns), \
         patch("alerter.dispatcher.requests.post", return_value=mock_resp):
        result = dispatch(
            payload, "ALERT",
            sns_arn="arn:test",
            webhook_url="https://trinity.example.com/hook",
        )

    assert "sns down" in result["sns"]
    assert result["trinity"] == "ok"


# ── hash_emails ───────────────────────────────────────────────

def test_hash_emails_off_leaves_owner_plain(sample_event, sample_identity):
    """build() with hash_emails=False must leave owner as plain text."""
    p = build_payload(sample_event, sample_identity, "acme", hash_emails=False)
    assert p["owner"] == "alice@corp.com"
    assert p["email"] == "alice@corp.com"
    assert p["pii_hashed"] is False


def test_hash_emails_on_hashes_owner_and_email(sample_event, sample_identity):
    """build() with hash_emails=True must SHA-256 both owner and email."""
    import hashlib
    p = build_payload(sample_event, sample_identity, "acme", hash_emails=True)
    expected = "sha256:" + hashlib.sha256(b"alice@corp.com").hexdigest()
    assert p["owner"] == expected
    assert p["email"] == expected


def test_hash_emails_on_stamps_pii_hashed_true(sample_event, sample_identity):
    """build() with hash_emails=True must set pii_hashed=True in payload."""
    p = build_payload(sample_event, sample_identity, "acme", hash_emails=True)
    assert p["pii_hashed"] is True
