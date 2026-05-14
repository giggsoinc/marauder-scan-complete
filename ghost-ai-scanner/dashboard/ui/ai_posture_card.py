# =============================================================
# FILE: dashboard/ui/ai_posture_card.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Single aggregated card replacing the numeric KPI row at
#          the top of the Inventory / Exec views.
#          One risk score, one band colour, one "what needs action"
#          breakdown. Drives the shift from "events log" UX to
#          "decision surface" UX.
# DEPENDS: streamlit, scoring.risk_score
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from scoring.risk_score import risk_score, risk_band, posture_breakdown  # noqa: E402


_CATEGORY_LABEL = {
    "process":              "AI processes running",
    "package":              "AI packages installed",
    "ide_plugin":           "IDE plugins detected",
    "browser":              "AI service browser hits",
    "container_image":      "Container images",
    "container_log_signal": "Container traffic / key signals",
    "shell_history":        "Past shell commands",
    "mcp_server":           "MCP servers configured",
    "agent_workflow":       "Agent workflows (n8n / Flowise / langflow)",
    "agent_scheduled":      "Scheduled agents (cron / launchd)",
    "tool_registration":    "@tool decorators in code",
    "vector_db":            "Local vector DBs",
}


def _band_colour(band: str) -> str:
    return {
        "CRITICAL": "#cf222e",
        "HIGH":     "#bc4c00",
        "MEDIUM":   "#9a6700",
        "LOW":      "#1f6feb",
        "CLEAN":    "#1a7f37",
    }.get(band, "#57606A")


def render_ai_posture(rows: list, device_label: str = "this fleet") -> None:
    """Render the aggregated AI Posture card.
    `rows` must be the COMPACTED rows (findings_current view) — one
    per signature, with severity/category/occurrences/last_seen.
    Falls back gracefully if older raw-finding rows are passed."""
    score = risk_score(rows)
    band  = risk_band(score)
    bdown = posture_breakdown(rows)
    open_categories = sum(1 for v in bdown.values() if v["count"] > 0)

    st.markdown(
        f"<div style='border:1px solid #d0d7de;border-radius:8px;"
        f"padding:18px 20px;margin:8px 0 18px;background:#ffffff'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;margin-bottom:14px'>"
        f"<div style='font-family:JetBrains Mono;font-size:12px;"
        f"letter-spacing:0.05em;text-transform:uppercase;color:#57606A'>"
        f"AI POSTURE — {device_label}</div>"
        f"<div style='font-family:JetBrains Mono;font-size:13px;"
        f"font-weight:600;color:{_band_colour(band)}'>"
        f"RISK SCORE: {score} / 100 &nbsp;·&nbsp; {band}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if open_categories == 0:
        st.markdown(
            "<div style='font-family:JetBrains Mono;font-size:13px;"
            "color:#1a7f37'>✓ No open AI findings. Posture is clean.</div></div>",
            unsafe_allow_html=True,
        )
        return

    # Render one row per non-empty category, sorted by severity then count.
    sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    items = sorted(
        bdown.items(),
        key=lambda kv: (-sev_rank.get(kv[1]["max_severity"], 0),
                        -kv[1]["count"]),
    )
    rows_html = []
    for cat, info in items:
        if info["count"] == 0:
            continue
        label    = _CATEGORY_LABEL.get(cat, cat.replace("_", " ").title())
        sev      = info["max_severity"]
        sev_clr  = _band_colour(sev)
        rows_html.append(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:center;padding:8px 0;border-top:1px solid #eaeef2'>"
            f"<div><span style='color:{sev_clr};font-weight:600'>● </span>"
            f"<span style='font-size:13px'>{info['count']} {label}</span></div>"
            f"<div style='font-family:JetBrains Mono;font-size:11px;"
            f"color:#57606A'>max sev: {sev}</div>"
            f"</div>"
        )
    st.markdown("".join(rows_html) + "</div>", unsafe_allow_html=True)
