# =============================================================
# FILE: dashboard/ui/header.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Top-of-page header strip — three-column layout showing
#          PATRONAI brand mark, "Updated Nm ago" freshness, and today's
#          date. Extracted from ghost_dashboard.py to honour the 150-LOC
#          cap when Phase 1A's asset-map route landed.
# DEPENDS: streamlit
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import os
from datetime import date

import streamlit as st

from .time_fmt import relative


def render_header(summary: dict) -> None:
    """Three-column header strip: brand · freshness · today's date.
    `summary['built_at']` is the data pipeline's last refresh timestamp."""
    company   = os.environ.get("COMPANY_NAME", "")
    built_at  = summary.get("built_at", "")
    rel       = relative(built_at)
    freshness = f"Updated {rel}" if rel else (built_at[:16] if built_at else "")

    c1, c2, c3 = st.columns([3, 5, 2])
    with c1:
        st.markdown(
            f'<span class="dot-green"></span>'
            f'<span style="font-family:JetBrains Mono;font-size:13px;'
            f'font-weight:600;color:#0D1117;">'
            f'PATRONAI · USER INTERFACE</span>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div style="text-align:center;font-family:JetBrains Mono;'
            f'font-size:11px;color:#57606A;">'
            f'{company + " · " if company else ""}{freshness}</div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div style="text-align:right;font-family:JetBrains Mono;'
            f'font-size:11px;color:#57606A;">{date.today().isoformat()}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<hr>", unsafe_allow_html=True)
