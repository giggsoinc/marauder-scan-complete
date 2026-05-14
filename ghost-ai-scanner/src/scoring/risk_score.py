# =============================================================
# FILE: src/scoring/risk_score.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Weighted risk-score calculation over a set of findings.
#          Drives the aggregated AI Posture card (one number instead
#          of a row-soup of severities). Pure functions — no I/O —
#          so unit-testable without S3 / Streamlit / Polars.
# DEPENDS: (stdlib only)
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial. Ships with feat/dashboard-posture.
# =============================================================

from collections import defaultdict
from typing import Iterable

# Per-severity weight contributed by ONE distinct signature. Tuned so a
# single CRITICAL finding (in a high-priority category like "process")
# crosses the CRITICAL band threshold of 75 on its own:
#   50 * 1.5 (process multiplier) = 75 → red. Locked in
#   test_one_critical_drives_red.
_SEV_WEIGHT = {
    "CRITICAL": 50,
    "HIGH":     12,
    "MEDIUM":    4,
    "LOW":       1,
}

# Category multipliers. A running process is more urgent than a stale
# shell history line even at the same severity. Applied after the
# severity weight.
_CATEGORY_MULT = {
    "process":              1.5,
    "mcp_server":           1.4,
    "agent_workflow":       1.3,
    "agent_scheduled":      1.3,
    "browser":              1.1,
    "container_log_signal": 1.2,
    "vector_db":            1.0,
    "package":              0.9,
    "ide_plugin":           0.9,
    "container_image":      0.8,
    "tool_registration":    0.7,
    "shell_history":        0.5,
}

# Cap — anything above this clamps to RED (100). Empirically a device
# with ~6 unauthorised running tools sits around 90; cap protects the
# UI from showing 4-digit "risk".
_SCORE_CAP = 100


def _row_weight(row: dict) -> float:
    """Score contribution from one compacted finding row."""
    if row.get("status") == "resolved":
        return 0.0
    sev = (row.get("severity") or "LOW").upper()
    cat = (row.get("category") or "").lower()
    base = _SEV_WEIGHT.get(sev, 1)
    mult = _CATEGORY_MULT.get(cat, 1.0)
    # Occurrences: log-dampened — a thing that re-appears 100 times is
    # not 100× as bad as seen once, but is worse than seen once.
    occ = int(row.get("occurrences") or 1)
    occ_factor = 1 + min(0.5, 0.05 * (occ - 1))
    return base * mult * occ_factor


def risk_score(rows: Iterable[dict]) -> int:
    """Aggregate risk score 0-100 for a set of compacted finding rows.
    Rows expected to come from findings_current (one per signature)."""
    total = sum(_row_weight(r) for r in rows)
    return int(min(_SCORE_CAP, round(total)))


def risk_band(score: int) -> str:
    """Human label for a 0-100 score — drives card colour."""
    if score >= 75:  return "CRITICAL"
    if score >= 40:  return "HIGH"
    if score >= 15:  return "MEDIUM"
    if score > 0:    return "LOW"
    return "CLEAN"


def posture_breakdown(rows: Iterable[dict]) -> dict:
    """Group OPEN signatures by category for the posture card.
    Returns {category: {count, max_severity, last_seen}}."""
    out: dict = defaultdict(lambda: {"count": 0, "max_severity": "LOW",
                                     "last_seen": ""})
    sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    for r in rows:
        if r.get("status") == "resolved":
            continue
        cat = r.get("category") or "unknown"
        slot = out[cat]
        slot["count"] += 1
        sev = (r.get("severity") or "LOW").upper()
        if sev_rank.get(sev, 0) > sev_rank.get(slot["max_severity"], 0):
            slot["max_severity"] = sev
        ls = r.get("last_seen") or ""
        if ls > slot["last_seen"]:
            slot["last_seen"] = ls
    return dict(out)
