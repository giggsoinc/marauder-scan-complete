# =============================================================
# FILE: tests/unit/test_chat_tools.py
# PROJECT: PatronAI — Marauder Scan
# VERSION: 2.0.0
# UPDATED: 2026-04-30
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Unit tests for rollup-backed chat tools. Mocks the
#          read_dimension_range seam — no S3, no LLM, stdlib only.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial — in-memory events list.
#   v2.0.0  2026-04-30  Rewritten for rollup-backed tools.
# =============================================================

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
# (removed: chat now lives under src/)
sys.path.insert(0, str(REPO / "src"))

from chat.tools import (  # noqa: E402
    get_summary_stats, get_top_risky_users, get_user_risk_profile,
    query_findings, get_fleet_status, get_shadow_ai_census,
    get_recent_activity, compare_periods,
)


# Canned rollup payloads matching the shape produced by hourly_rollup.py.

_BY_PROVIDER = {
    "OpenAI ChatGPT":  {"hits": 47, "users": ["alice@x.com", "bob@x.com"],
                        "user_count": 2, "device_count": 2,
                        "categories": {"browser": 47},
                        "by_severity": {"HIGH": 47},
                        "first_seen": "2026-04-01T00:00:00+00:00",
                        "last_seen":  "2026-04-29T00:00:00+00:00"},
    "GitHub Copilot":  {"hits": 12, "users": ["alice@x.com"],
                        "user_count": 1, "device_count": 1,
                        "categories": {"ide_plugin": 12},
                        "by_severity": {"MEDIUM": 12},
                        "first_seen": "2026-04-05T00:00:00+00:00",
                        "last_seen":  "2026-04-28T00:00:00+00:00"},
}

_BY_USER = {
    "alice@x.com": {"hits": 30, "providers": ["OpenAI ChatGPT", "GitHub Copilot"],
                    "provider_count": 2, "device_count": 1,
                    "categories": {"browser": 25, "ide_plugin": 5},
                    "by_severity": {"HIGH": 25, "MEDIUM": 5},
                    "total_risk": 82.5, "first_seen": "2026-04-01T00:00:00+00:00",
                    "last_seen":  "2026-04-29T00:00:00+00:00"},
    "bob@x.com":   {"hits": 15, "providers": ["OpenAI ChatGPT"],
                    "provider_count": 1, "device_count": 1,
                    "categories": {"browser": 15},
                    "by_severity": {"HIGH": 15},
                    "total_risk": 45.0, "first_seen": "2026-04-10T00:00:00+00:00",
                    "last_seen":  "2026-04-28T00:00:00+00:00"},
}

_BY_SEVERITY = {"HIGH": 47, "MEDIUM": 12}

_BY_DEVICE = {
    "alice-mbp": {"hits": 30, "user_count": 1, "device_count": 0,
                  "by_severity": {"HIGH": 25, "MEDIUM": 5}},
    "bob-mbp":   {"hits": 15, "user_count": 1, "device_count": 0,
                  "by_severity": {"HIGH": 15}},
}

_BY_CATEGORY = {
    "browser":    {"hits": 40, "user_count": 2, "device_count": 0,
                   "by_severity": {"HIGH": 40}},
    "ide_plugin": {"hits": 5,  "user_count": 1, "device_count": 0,
                   "by_severity": {"MEDIUM": 5}},
}


def _fake_reader(scope, scope_id, dimension, start, end, max_workers=None):
    """Mock — returns canned dim payloads regardless of window."""
    return {
        "provider": _BY_PROVIDER,
        "user":     _BY_USER,
        "severity": _BY_SEVERITY,
        "device":   _BY_DEVICE,
        "category": _BY_CATEGORY,
    }.get(dimension, {})


def _fake_empty_reader(*a, **kw):
    return {}


# ── Tool 1: get_summary_stats ───────────────────────────────────


def test_summary_stats_tenant_scope():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_summary_stats("tenant", "abc1234567890def", days_back=30)
    assert r["total_findings"] == 47 + 12
    assert r["severities"] == {"HIGH": 47, "MEDIUM": 12}
    assert r["unique_users"] == 2
    assert r["unique_providers"] == 2
    assert r["window_days"] == 30
    assert r["scope"] == "tenant"


def test_summary_stats_user_scope_unique_users_is_one():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_summary_stats("user", "abc1234567890def")
    assert r["unique_users"] == 1   # user-scope = themselves


def test_summary_stats_empty_rollup_returns_no_data_envelope():
    """When nothing has been rolled up, tool returns the no_data envelope
    so the LLM can say so honestly instead of fabricating."""
    with patch("chat.tools.read_dimension_range", side_effect=_fake_empty_reader):
        r = get_summary_stats("tenant", "abc")
    assert r.get("no_data") is True
    assert "_citation" in r


# ── Tool 2: get_top_risky_users ─────────────────────────────────


def test_top_risky_users_sorted_by_total_risk():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_top_risky_users("tenant", "abc", n=5)
    rows = r["users"]
    assert rows[0]["user"] == "alice@x.com"
    assert rows[0]["total_risk"] == 82.5
    assert rows[1]["user"] == "bob@x.com"
    assert "_citation" in r and r["_citation"]["scope"] == "tenant"


def test_top_risky_users_caps_n():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_top_risky_users("tenant", "abc", n=1)
    assert len(r["users"]) == 1


def test_top_risky_users_no_data():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_empty_reader):
        r = get_top_risky_users("tenant", "abc")
    assert r.get("no_data") is True
    assert "_citation" in r


# ── Tool 3: get_user_risk_profile ───────────────────────────────


def test_user_risk_profile_tenant_lookup_hits():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_user_risk_profile("tenant", "abc", "alice@x.com")
    assert r["found"] is True
    assert r["total_findings"] == 30
    assert "OpenAI ChatGPT" in r["providers"]


def test_user_risk_profile_tenant_lookup_miss():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_user_risk_profile("tenant", "abc", "nobody@x.com")
    assert r["found"] is False


def test_user_risk_profile_user_scope_uses_severity_dim():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_user_risk_profile("user", "abc", "alice@x.com")
    assert r["found"] is True
    assert r["total_findings"] == 47 + 12   # sum of severity counts


# ── Tool 4: query_findings ──────────────────────────────────────


def test_query_findings_severity_filter():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = query_findings("tenant", "abc", severity="HIGH")
    matches = r["matches"]
    # OpenAI ChatGPT has 47 HIGH; Copilot has 0 HIGH so excluded.
    assert any(m["provider"] == "OpenAI ChatGPT" for m in matches)
    assert not any(m["provider"] == "GitHub Copilot" for m in matches)


def test_query_findings_no_filters_returns_all():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = query_findings("tenant", "abc")
    assert r["match_count"] == 2


def test_query_findings_user_filter():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = query_findings("tenant", "abc", user="bob@x.com")
    # Only OpenAI ChatGPT has bob@x.com.
    assert {m["provider"] for m in r["matches"]} == {"OpenAI ChatGPT"}


# ── Tool 5: get_fleet_status ────────────────────────────────────


def test_fleet_status_counts_devices():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_fleet_status("tenant", "abc")
    assert r["total_devices"] == 2
    assert r["top_devices"][0]["device"] == "alice-mbp"


# ── Tool 6: get_shadow_ai_census (the headline) ─────────────────


def test_shadow_ai_census_sorted_by_hits_desc():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_shadow_ai_census("tenant", "abc")
    provs = r["providers"]
    assert provs[0]["provider"] == "OpenAI ChatGPT"
    assert provs[0]["hits"] == 47
    assert provs[0]["user_count"] == 2
    assert provs[1]["provider"] == "GitHub Copilot"
    assert "_citation" in r
    assert r["_citation"]["source"] == "S3 hourly rollups"


def test_shadow_ai_census_human_names_preserved():
    """Critical: provider names must already be human (normalised at rollup time)."""
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        names = [p["provider"]
                 for p in get_shadow_ai_census("tenant", "abc")["providers"]]
    assert "claude.ai" not in names
    assert "github.copilot" not in names
    assert "OpenAI ChatGPT" in names
    assert "GitHub Copilot" in names


def test_shadow_ai_census_no_data():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_empty_reader):
        r = get_shadow_ai_census("tenant", "abc")
    assert r.get("no_data") is True
    assert "_citation" in r


# ── Tool 7: get_recent_activity ─────────────────────────────────


def test_recent_activity_returns_severity_breakdown():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = get_recent_activity("tenant", "abc", hours=24)
    assert r["window_hours"] == 24
    assert r["total_findings"] == 47 + 12
    assert r["by_severity"] == {"HIGH": 47, "MEDIUM": 12}


# ── Tool 8: compare_periods ─────────────────────────────────────


def test_compare_periods_zero_when_identical():
    with patch("chat.tools.read_dimension_range", side_effect=_fake_reader):
        r = compare_periods("tenant", "abc",
                            "2026-04-01", "2026-04-14",
                            "2026-04-15", "2026-04-29")
    # Same canned data both windows → delta = 0.
    assert r["delta_findings"] == 0
    assert r["new_providers"] == []
    assert r["new_users"] == []
