# =============================================================
# FILE: tests/unit/test_backfill.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Unit tests for Summarizer.backfill(), run_now(), and
#          CursorStore.reset() — all external S3 calls mocked.
#          Verifies: correct number of days iterated, empty days
#          skipped, today-default on run_now, cursor reset to None.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call

import polars as pl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from summarizer.summarizer import Summarizer


# ── helpers ───────────────────────────────────────────────────

def _make_store(findings_by_date: dict = None) -> MagicMock:
    """
    Build a mock BlobIndexStore.
    findings_by_date: {iso_date: polars.DataFrame} — returned only for
    severity='high'; other severity calls return empty to avoid 4× inflation.
    All other dates return an empty DataFrame.
    """
    findings_by_date = findings_by_date or {}
    store            = MagicMock()

    def fake_findings_read(target_date, severity="high", limit=500):
        # Only return data on the "high" severity call to keep counts exact.
        if severity != "high":
            return pl.DataFrame()
        return findings_by_date.get(target_date, pl.DataFrame())

    store.findings.read.side_effect = fake_findings_read
    store.summary.write.return_value = True
    return store


def _sample_df(n: int = 3) -> pl.DataFrame:
    """Return a minimal findings DataFrame with n rows."""
    return pl.DataFrame({
        "src_ip":   [f"10.0.0.{i}" for i in range(n)],
        "provider": ["openai.com"] * n,
        "severity": ["HIGH"] * n,
        "outcome":  ["DOMAIN_ALERT"] * n,
        "timestamp": ["2026-04-19T10:00:00Z"] * n,
    })


# ── backfill ──────────────────────────────────────────────────

def test_backfill_returns_only_days_with_data():
    """backfill(5) must return only dates that had findings, skipping empties."""
    today = date.today().isoformat()
    store = _make_store({today: _sample_df(5)})

    results = Summarizer(store).backfill(days=5)

    assert len(results) == 1
    assert results[0]["total_events"] == 5


def test_backfill_iterates_correct_number_of_days():
    """backfill(N) must call findings.read exactly N×4 times (4 severities)."""
    store = _make_store()
    Summarizer(store).backfill(days=7)
    # 7 days × 4 severities = 28 calls
    assert store.findings.read.call_count == 7 * 4


def test_backfill_writes_summary_for_every_day():
    """backfill() must write a summary for every date — even empty ones.
    Empty summaries keep Grafana from showing gaps in the timeline."""
    today  = date.today().isoformat()
    yest   = (date.today() - timedelta(days=1)).isoformat()
    store  = _make_store({today: _sample_df(2), yest: _sample_df(4)})

    Summarizer(store).backfill(days=5)

    # All 5 days get a summary written — not just the 2 with data
    assert store.summary.write.call_count == 5


def test_backfill_empty_bucket_returns_empty_list():
    """backfill() on an empty bucket must return [] (no days with events).
    Summaries are still written for every day so Grafana shows zero not missing."""
    store   = _make_store()
    results = Summarizer(store).backfill(days=10)
    assert results == []
    # 10 zero-event summaries written — one per day
    assert store.summary.write.call_count == 10


def test_backfill_includes_build_mode_backfill():
    """Every summary written during backfill must have build_mode='backfill'."""
    today = date.today().isoformat()
    store = _make_store({today: _sample_df(1)})

    results = Summarizer(store).backfill(days=3)
    assert results[0]["build_mode"] == "backfill"


# ── run_now ───────────────────────────────────────────────────

def test_run_now_defaults_to_today():
    """run_now() with no argument must build summary for today's date."""
    today = date.today().isoformat()
    store = _make_store({today: _sample_df(3)})

    result = Summarizer(store).run_now()

    assert result["build_mode"]   == "on_demand"
    assert result["total_events"] == 3


def test_run_now_accepts_explicit_date():
    """run_now('2026-01-01') must build summary for that specific date."""
    target = "2026-01-01"
    store  = _make_store({target: _sample_df(7)})

    result = Summarizer(store).run_now(target_date=target)

    assert result["total_events"] == 7


def test_run_now_includes_build_duration():
    """run_now() must return build_duration_seconds >= 0."""
    store  = _make_store()
    result = Summarizer(store).run_now()
    assert result["build_duration_seconds"] >= 0


# ── cursor reset ─────────────────────────────────────────────

def test_cursor_reset_writes_null_last_key():
    """CursorStore.reset() must write last_key=None to S3."""
    import json
    from store.cursor_store import CursorStore

    store        = CursorStore.__new__(CursorStore)
    captured     = {}

    def fake_put(key, data):
        captured["key"]   = key
        captured["state"] = json.loads(data)
        return True

    store._put = fake_put
    store.reset()

    assert captured["state"]["last_key"]           is None
    assert captured["state"]["files_processed"]    == 0


def test_cursor_reset_returns_true_on_success():
    """CursorStore.reset() must return True when S3 write succeeds."""
    from store.cursor_store import CursorStore

    store      = CursorStore.__new__(CursorStore)
    store._put = MagicMock(return_value=True)

    assert store.reset() is True
