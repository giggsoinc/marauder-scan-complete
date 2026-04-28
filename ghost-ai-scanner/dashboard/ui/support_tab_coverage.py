# =============================================================
# FILE: dashboard/ui/support_tab_coverage.py
# VERSION: 2.0.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: Support COVERAGE tab — checks known gap providers against
#          the live unauthorized.csv denylist. Real data only.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-20  Remove synthetic demo fallback — real data only
# =============================================================

import io
import logging

import pandas as pd
import streamlit as st

log = logging.getLogger("patronai.ui.support_coverage")

_KNOWN_GAPS = ["n8n Cloud", "Langflow", "Dify", "sim.ai", "Google Opal"]
_BADGE_OK   = '<span class="badge badge-clean">IN DENYLIST</span>'
_BADGE_MISS = '<span class="badge badge-critical">MISSING</span>'


def render_coverage(store) -> None:
    """Coverage tab — verify known gap providers exist in unauthorized.csv."""
    if store is None:
        st.info("Storage not configured — connect S3 to view coverage check.")
        return

    denylist_names = _load_denylist_names(store)

    st.markdown('<div class="card-title">KNOWN PROVIDER GAP CHECK</div>',
                unsafe_allow_html=True)

    missing_count = 0
    rows = []
    for provider in _KNOWN_GAPS:
        found = any(provider.lower() in name.lower() for name in denylist_names)
        badge = _BADGE_OK if found else _BADGE_MISS
        if not found:
            missing_count += 1
        rows.append(
            f"<tr><td style='font-size:12px'>{provider}</td><td>{badge}</td></tr>"
        )

    st.markdown(
        f"<table><thead><tr><th>PROVIDER</th><th>STATUS</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if not denylist_names:
        st.info("No denylist loaded — add providers in Settings → Provider Lists.")
    elif missing_count:
        st.warning(f"{missing_count} provider(s) missing from denylist. "
                   "Add them in Settings → Provider Lists.")
    else:
        st.success("All known gap providers are in the denylist.")

    if denylist_names:
        with st.expander(f"Full denylist — {len(denylist_names)} providers"):
            for n in sorted(set(denylist_names)):
                st.markdown(
                    f'<span style="font-family:JetBrains Mono;font-size:11px;">{n}</span>',
                    unsafe_allow_html=True,
                )


def _load_denylist_names(store) -> list:
    """Return provider names from unauthorized.csv in S3."""
    try:
        raw = store.settings._get("config/unauthorized.csv")
        if not raw:
            return []
        lines = [l for l in raw.decode().splitlines() if not l.startswith("#")]
        df = pd.read_csv(io.StringIO("\n".join(lines)))
        return df["name"].dropna().tolist() if "name" in df.columns else []
    except Exception as e:
        log.warning("_load_denylist_names failed: %s", e)
        return []
