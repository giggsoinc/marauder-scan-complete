# =============================================================
# FILE: tests/unit/test_cursor_migration.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the Step 0.5 cursor contract:
#          - First-run cursor is empty (cursor_ts=None).
#          - Legacy v1 cursors (only last_key + last_processed_at) get
#            migrated to v2 with cursor_ts seeded one hour before the last
#            write — so the dashboard back-fills the most recent hour on
#            first run after upgrade.
#          - Corrupt cursor file resets cleanly.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Step 0.5.
# =============================================================

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import pytest  # noqa: E402

# CursorStore lives under src/store/, whose __init__.py imports FindingsStore
# which requires polars at runtime. Dev environments without polars binaries
# skip this module rather than fail collection. Production / CI has polars.
pytest.importorskip("polars", reason="polars binary required to import store package")

from store.cursor_store import CursorStore  # noqa: E402


def _store_with_raw(raw_value: bytes):
    """Build a CursorStore whose _get returns the supplied raw bytes."""
    s = CursorStore.__new__(CursorStore)
    s._get = MagicMock(return_value=raw_value)
    s._put = MagicMock(return_value=True)
    return s


def test_first_run_returns_safe_defaults():
    s = _store_with_raw(b"")  # _get returns empty
    state = s.read()
    assert state["cursor_ts"]         is None
    assert state["last_key"]          is None
    assert state["files_processed"]   == 0


def test_corrupt_file_resets():
    s = _store_with_raw(b"this is not json {")
    state = s.read()
    assert state["cursor_ts"] is None
    assert state["last_key"]  is None


def test_legacy_v1_cursor_migrates_to_seeded_v2():
    """v1 cursor with last_key + last_processed_at → cursor_ts = lpa - 1h."""
    lpa = "2026-04-26T03:55:00+00:00"
    legacy = json.dumps({
        "last_key":          "ocsf/agent/scans/abc/latest.json",
        "last_processed_at": lpa,
        "files_processed":   1,
        "total_events":      0,
    }).encode()
    s = _store_with_raw(legacy)
    state = s.read()

    assert state["cursor_ts"] is not None
    seeded = datetime.fromisoformat(state["cursor_ts"])
    expected = datetime.fromisoformat(lpa) - timedelta(hours=1)
    assert seeded == expected
    assert state["last_key"] == "ocsf/agent/scans/abc/latest.json"


def test_v2_cursor_passes_through_unchanged():
    """v2 cursor with explicit cursor_ts shouldn't be re-seeded."""
    cts = "2026-04-26T04:00:00+00:00"
    raw = json.dumps({
        "cursor_ts":         cts,
        "last_key":          "ocsf/agent/heartbeats/x/latest.json",
        "last_processed_at": "2026-04-26T04:00:30+00:00",
        "files_processed":   3,
        "total_events":      12,
    }).encode()
    s = _store_with_raw(raw)
    state = s.read()
    assert state["cursor_ts"] == cts


def test_write_persists_cursor_ts():
    s = _store_with_raw(b"")
    when = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    s.write(cursor_ts=when, last_key="k", files_processed=5, total_events=100)
    s._put.assert_called_once()
    body = json.loads(s._put.call_args[0][1])
    assert body["cursor_ts"]         == when.isoformat()
    assert body["last_key"]          == "k"
    assert body["files_processed"]   == 5
    assert body["total_events"]      == 100


def test_write_with_none_cursor_persists_null():
    s = _store_with_raw(b"")
    s.write(cursor_ts=None, last_key="", files_processed=0)
    body = json.loads(s._put.call_args[0][1])
    assert body["cursor_ts"] is None


def test_legacy_cursor_without_lpa_falls_through():
    """Legacy cursor missing both cursor_ts and last_processed_at → defaults."""
    raw = json.dumps({"last_key": "x", "files_processed": 0}).encode()
    s = _store_with_raw(raw)
    state = s.read()
    assert state["cursor_ts"] is None
    assert state["last_key"]  == "x"
