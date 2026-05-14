# =============================================================
# FILE: tests/unit/test_risk_score.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc
# PURPOSE: Lock the risk scoring contract — drives the AI Posture
#          card. If these numbers drift, the headline UX drifts.
# =============================================================

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from scoring.risk_score import (
    risk_score, risk_band, posture_breakdown,
)


def _row(sev="HIGH", cat="process", occ=1, status="open"):
    return {"severity": sev, "category": cat, "occurrences": occ,
            "status": status}


def test_empty_input_is_clean():
    assert risk_score([]) == 0
    assert risk_band(0) == "CLEAN"


def test_resolved_rows_do_not_score():
    rows = [_row(sev="CRITICAL", status="resolved")]
    assert risk_score(rows) == 0


def test_single_high_process_contributes():
    s = risk_score([_row(sev="HIGH", cat="process")])
    assert s > 0
    assert s < 75  # one HIGH shouldn't pin red


def test_one_critical_drives_red():
    """A single CRITICAL finding alone must push the device to CRITICAL band."""
    s = risk_score([_row(sev="CRITICAL", cat="process")])
    assert risk_band(s) == "CRITICAL", f"score={s} expected CRITICAL band"


def test_score_caps_at_100():
    rows = [_row(sev="CRITICAL", cat="process") for _ in range(50)]
    assert risk_score(rows) == 100


def test_category_multiplier_applied():
    """A running process scores higher than a stale shell-history line."""
    proc = risk_score([_row(sev="HIGH", cat="process")])
    hist = risk_score([_row(sev="HIGH", cat="shell_history")])
    assert proc > hist


def test_occurrences_dampened():
    """Seen 100 times is worse than seen once but not 100×."""
    once = risk_score([_row(sev="HIGH", cat="process", occ=1)])
    many = risk_score([_row(sev="HIGH", cat="process", occ=100)])
    assert many > once
    assert many < once * 10


def test_band_thresholds():
    assert risk_band(0)   == "CLEAN"
    assert risk_band(5)   == "LOW"
    assert risk_band(20)  == "MEDIUM"
    assert risk_band(50)  == "HIGH"
    assert risk_band(80)  == "CRITICAL"
    assert risk_band(100) == "CRITICAL"


# ── posture_breakdown ──────────────────────────────────────────

def test_posture_breakdown_groups_by_category():
    rows = [
        _row(cat="process", sev="HIGH"),
        _row(cat="process", sev="CRITICAL"),
        _row(cat="vector_db", sev="MEDIUM"),
    ]
    b = posture_breakdown(rows)
    assert b["process"]["count"] == 2
    assert b["process"]["max_severity"] == "CRITICAL"
    assert b["vector_db"]["count"] == 1


def test_posture_breakdown_skips_resolved():
    rows = [
        _row(cat="process", status="open"),
        _row(cat="process", status="resolved"),
    ]
    b = posture_breakdown(rows)
    assert b["process"]["count"] == 1


def test_posture_breakdown_picks_latest_last_seen():
    rows = [
        {"category": "process", "severity": "HIGH",
         "occurrences": 1, "last_seen": "2026-05-10T00:00:00"},
        {"category": "process", "severity": "HIGH",
         "occurrences": 1, "last_seen": "2026-05-11T12:00:00"},
    ]
    b = posture_breakdown(rows)
    assert b["process"]["last_seen"] == "2026-05-11T12:00:00"
