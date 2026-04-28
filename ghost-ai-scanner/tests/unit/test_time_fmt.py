# =============================================================
# FILE: tests/unit/test_time_fmt.py
# PROJECT: PatronAI — Phase 1B
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the time-format helper:
#          - DD-MMM-YY HH24:MM:SS TZ shape
#          - viewer's local timezone applied
#          - returns '' on empty / unparseable input
#          - relative() produces sensible "Nm/Nh/Nd ago"
#          - tooltip() echoes UTC ISO
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1B.
# =============================================================

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard"))


def test_fmt_basic_shape():
    from ui.time_fmt import fmt
    s = fmt("2026-04-26T14:30:45+00:00", tz_name="UTC")
    # Expect: 26-APR-26 14:30:45 UTC
    assert re.fullmatch(r"\d{2}-[A-Z]{3}-\d{2} \d{2}:\d{2}:\d{2} \w+", s), s
    assert s.startswith("26-APR-26")
    assert s.endswith("UTC")


def test_fmt_converts_to_named_tz():
    from ui.time_fmt import fmt
    # UTC 12:00 → IST 17:30
    s = fmt("2026-04-26T12:00:00+00:00", tz_name="Asia/Kolkata")
    assert "17:30:00 IST" in s
    assert s.startswith("26-APR-26")


def test_fmt_handles_z_suffix():
    from ui.time_fmt import fmt
    s = fmt("2026-04-26T14:30:45Z", tz_name="UTC")
    assert "14:30:45 UTC" in s


def test_fmt_handles_naive_iso_assumes_utc():
    from ui.time_fmt import fmt
    s = fmt("2026-04-26T14:30:45", tz_name="UTC")
    assert "14:30:45 UTC" in s


def test_fmt_returns_empty_on_none():
    from ui.time_fmt import fmt
    assert fmt(None) == ""
    assert fmt("")  == ""


def test_fmt_returns_empty_on_garbage():
    from ui.time_fmt import fmt
    assert fmt("not a timestamp")    == ""
    assert fmt("2026-13-99T99:99:99") == ""


def test_fmt_accepts_datetime_directly():
    from ui.time_fmt import fmt
    dt = datetime(2026, 4, 26, 14, 30, 45, tzinfo=timezone.utc)
    s = fmt(dt, tz_name="UTC")
    assert "14:30:45 UTC" in s


def test_fmt_month_lookup_table():
    """All 12 months render as 3-letter uppercase abbreviations."""
    from ui.time_fmt import fmt
    abbrs = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    for m, abbr in enumerate(abbrs, 1):
        iso = f"2026-{m:02d}-15T00:00:00+00:00"
        s = fmt(iso, tz_name="UTC")
        assert f"-{abbr}-26" in s, f"month {m}: {s}"


def test_fmt_unknown_tz_falls_back_to_utc():
    from ui.time_fmt import fmt
    s = fmt("2026-04-26T14:30:45+00:00", tz_name="Mars/Olympus_Mons")
    # Either accepts the IANA fallback label OR drops to UTC
    assert "UTC" in s or "Olympus_Mons" in s


# ── relative() ──────────────────────────────────────────────────

def test_relative_just_now():
    from ui.time_fmt import relative
    now = datetime.now(timezone.utc).isoformat()
    assert relative(now) == "just now"


def test_relative_minutes():
    from ui.time_fmt import relative
    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert relative(five_min_ago) == "5m ago"


def test_relative_hours():
    from ui.time_fmt import relative
    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert relative(two_hours_ago) == "2h ago"


def test_relative_days():
    from ui.time_fmt import relative
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert relative(three_days_ago) == "3d ago"


def test_relative_empty_on_miss():
    from ui.time_fmt import relative
    assert relative("")   == ""
    assert relative(None) == ""


# ── tooltip() ────────────────────────────────────────────────────

def test_tooltip_round_trips_iso():
    from ui.time_fmt import tooltip
    out = tooltip("2026-04-26T14:30:45+00:00")
    assert "2026-04-26" in out
    assert "14:30:45"   in out


def test_tooltip_empty_on_garbage():
    from ui.time_fmt import tooltip
    assert tooltip("nope") == ""


# ── LOC cap ──────────────────────────────────────────────────────

def test_time_fmt_under_loc_cap():
    body = (REPO / "dashboard" / "ui" / "time_fmt.py").read_text()
    assert len(body.splitlines()) <= 150
