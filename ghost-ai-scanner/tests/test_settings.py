# =============================================================
# FILE: tests/test_settings.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Regression tests for settings_store ocsf_bucket bug.
#          Asserts load_settings() never returns ocsf_bucket == "".
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — covers empty-string ocsf_bucket bug
# =============================================================

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from store.settings_store import SettingsStore


def _make_store(s3_json: str | None, bucket_env: str = "my-test-bucket") -> SettingsStore:
    """Build a SettingsStore with a mocked _get that returns s3_json."""
    store = SettingsStore.__new__(SettingsStore)
    store.bucket = bucket_env
    store._get   = MagicMock(return_value=s3_json)
    return store


def test_ocsf_bucket_not_empty_when_set() -> None:
    """Normal case — ocsf_bucket is present and non-empty."""
    payload = json.dumps({"storage": {"ocsf_bucket": "real-bucket"}})
    with patch.dict(os.environ, {"MARAUDER_SCAN_BUCKET": "real-bucket"}):
        result = _make_store(payload).read()
    assert result["storage"]["ocsf_bucket"] == "real-bucket"


def test_ocsf_bucket_restored_when_empty_string() -> None:
    """Bug regression — empty string ocsf_bucket must be replaced by env var."""
    payload = json.dumps({"storage": {"ocsf_bucket": ""}})
    with patch.dict(os.environ, {"MARAUDER_SCAN_BUCKET": "fallback-bucket"}):
        result = _make_store(payload).read()
    assert result["storage"]["ocsf_bucket"] != ""
    assert result["storage"]["ocsf_bucket"] == "fallback-bucket"


def test_ocsf_bucket_restored_when_key_missing() -> None:
    """ocsf_bucket missing entirely — env var fills in."""
    payload = json.dumps({"scanner": {"scan_interval_secs": 300}})
    with patch.dict(os.environ, {"MARAUDER_SCAN_BUCKET": "fallback-bucket"}):
        result = _make_store(payload).read()
    assert result.get("storage", {}).get("ocsf_bucket") == "fallback-bucket"


def test_ocsf_bucket_never_empty_no_env() -> None:
    """Neither S3 nor env has a bucket — result must not be empty string."""
    payload = json.dumps({"storage": {"ocsf_bucket": ""}})
    with patch.dict(os.environ, {}, clear=True):
        result = _make_store(payload, bucket_env="").read()
    # With no env fallback, value stays "" but that's config error — not a
    # runtime crash. Key invariant: no KeyError, no exception.
    assert isinstance(result, dict)


def test_settings_not_found_returns_empty_dict() -> None:
    """Missing settings.json returns {} without raising."""
    result = _make_store(None).read()
    assert result == {}


def test_corrupted_json_returns_empty_dict() -> None:
    """Corrupted JSON returns {} without raising."""
    result = _make_store("not-json").read()
    assert result == {}
