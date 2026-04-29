# =============================================================
# FILE: tests/unit/test_chat_tools.py
# PROJECT: PatronAI — Marauder Scan
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Unit tests for 8 pure-analytics chat tool functions.
#          No Streamlit, AWS, or LLM — stdlib only.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard"))

from ui.chat.tools import (  # noqa: E402
    get_summary_stats, get_top_risky_users, get_user_risk_profile,
    query_findings, get_fleet_status, get_shadow_ai_census,
    get_recent_activity, compare_periods,
)

OLD = "2020-01-01T00:00:00+00:00"   # guaranteed > 24 h ago


def _ev(outcome="ENDPOINT_FINDING", severity="HIGH", email="alice@x.com",
        host="alice-mbp", provider="mcp:cf:fs", category="mcp_server",
        ts="2026-04-28T10:00:00+00:00") -> dict:
    return {"outcome": outcome, "severity": severity, "email": email,
            "src_hostname": host, "provider": provider,
            "category": category, "timestamp": ts}


# ── Tool 1 ─────────────────────────────────────────────────────
def test_summary_stats_empty():
    r = get_summary_stats([])
    assert r["total_findings"] == 0 and r["unique_users"] == 0

def test_summary_stats_single_finding():
    r = get_summary_stats([_ev()])
    assert r["total_findings"] == 1 and r["severities"] == {"HIGH": 1}

def test_summary_stats_ignores_non_findings():
    r = get_summary_stats([_ev(), _ev(outcome="HEARTBEAT")])
    assert r["total_findings"] == 1 and r["total_events"] == 2


# ── Tool 2 ─────────────────────────────────────────────────────
def test_top_risky_users_empty():
    assert get_top_risky_users([]) == []

def test_top_risky_users_n_caps_results():
    evs = [_ev(email="alice@x.com"), _ev(email="bob@x.com"), _ev(email="carol@x.com")]
    assert len(get_top_risky_users(evs, n=2)) == 2

def test_top_risky_users_max_severity():
    evs = [_ev(email="alice@x.com", severity="LOW"),
           _ev(email="alice@x.com", severity="CRITICAL")]
    assert get_top_risky_users(evs)[0]["max_severity"] == "CRITICAL"


# ── Tool 3 ─────────────────────────────────────────────────────
def test_user_risk_profile_empty():
    r = get_user_risk_profile([], "nobody@x.com")
    assert r["total_findings"] == 0 and r["providers"] == []

def test_user_risk_profile_scopes_to_user():
    evs = [_ev(email="alice@x.com"), _ev(email="bob@x.com")]
    r = get_user_risk_profile(evs, "alice@x.com")
    assert r["total_findings"] == 1 and "alice-mbp" in r["devices"]


# ── Tool 4 ─────────────────────────────────────────────────────
def test_query_findings_empty():
    assert query_findings([]) == []

def test_query_findings_severity_filter():
    evs = [_ev(severity="HIGH"), _ev(severity="LOW")]
    r = query_findings(evs, severity="HIGH")
    assert len(r) == 1 and r[0]["severity"] == "HIGH"

def test_query_findings_user_filter():
    evs = [_ev(email="alice@x.com"), _ev(email="bob@x.com")]
    r = query_findings(evs, user="alice@x.com")
    assert len(r) == 1 and r[0]["user"] == "alice@x.com"

def test_query_findings_only_endpoint_findings():
    assert len(query_findings([_ev(), _ev(outcome="HEARTBEAT")])) == 1


# ── Tool 5 ─────────────────────────────────────────────────────
def test_fleet_status_empty():
    r = get_fleet_status([])
    assert r["total_devices"] == 0 and r["silent_24h"] == 0

def test_fleet_status_recent_not_silent():
    r = get_fleet_status([_ev()])
    assert r["total_devices"] == 1 and r["silent_24h"] == 0

def test_fleet_status_old_device_is_silent():
    r = get_fleet_status([_ev(ts=OLD, host="ghost-box")])
    assert r["silent_24h"] == 1 and "ghost-box" in r["silent_hosts"]


# ── Tool 6 ─────────────────────────────────────────────────────
def test_shadow_ai_census_empty():
    assert get_shadow_ai_census([]) == []

def test_shadow_ai_census_sorted_by_users_desc():
    evs = [_ev(provider="p1", email="alice@x.com"),
           _ev(provider="p2", email="alice@x.com"),
           _ev(provider="p2", email="bob@x.com")]
    r = get_shadow_ai_census(evs)
    assert r[0]["provider"] == "p2" and r[0]["users"] == 2


# ── Tool 7 ─────────────────────────────────────────────────────
def test_recent_activity_empty():
    assert get_recent_activity([]) == []

def test_recent_activity_excludes_old():
    evs = [_ev(), _ev(ts=OLD, email="ghost@x.com")]
    users = [row["user"] for row in get_recent_activity(evs, hours=24)]
    assert "ghost@x.com" not in users


# ── Tool 8 ─────────────────────────────────────────────────────
def test_compare_periods_empty():
    r = compare_periods([], "2026-04-01", "2026-04-15", "2026-04-16", "2026-04-30")
    assert r["delta_findings"] == 0 and r["new_providers"] == []

def test_compare_periods_delta_and_new_users():
    p1e = _ev(ts="2026-04-05T00:00:00+00:00", email="alice@x.com", provider="p1")
    p2e = _ev(ts="2026-04-20T00:00:00+00:00", email="bob@x.com",   provider="p2")
    r = compare_periods([p1e, p2e],
                        "2026-04-01", "2026-04-15",
                        "2026-04-16", "2026-04-30")
    assert r["delta_findings"] == 0   # 1 each period
    assert "p2" in r["new_providers"] and "bob@x.com" in r["new_users"]
