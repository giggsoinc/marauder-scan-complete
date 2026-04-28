# =============================================================
# FILE: dashboard/ui/support_tab_rules.py
# VERSION: 2.0.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: Support RULES tab — network denylist and code pattern counts,
#          category breakdown, inline CSV preview. Real data only.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-20  Remove synthetic demo fallback — real data only
# =============================================================

import io
import logging
from collections import Counter

import pandas as pd
import streamlit as st

log = logging.getLogger("patronai.ui.support_rules")


def render_rules(store) -> None:
    """Rules tab — denylist counts, category breakdown, inline preview."""
    if store is None:
        st.info("Storage not configured — connect S3 to view rule counts.")
        return

    net_rows   = _load_csv(store, "config/unauthorized.csv")
    code_count = _load_code_count(store)

    c1, c2, c3 = st.columns(3)
    c1.metric("Network rules",  len(net_rows) if net_rows else 0)
    c2.metric("Code patterns",  code_count)
    c3.metric("Categories",
              len(set(r.get("category", "") for r in net_rows)) if net_rows else 0)

    if net_rows:
        cats = Counter(r.get("category", "Unknown") for r in net_rows)
        st.markdown('<div class="card-title">BY CATEGORY</div>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame([{"Category": k, "Rules": v} for k, v in cats.most_common()]),
            use_container_width=True, hide_index=True,
        )
        st.markdown('<div class="card-title">NETWORK DENYLIST</div>',
                    unsafe_allow_html=True)
        preview_cols = [c for c in ("name", "category", "domain", "port", "severity")
                        if c in net_rows[0]]
        # Phase 1B — wrap with filtered_table so the user can search the
        # full denylist instead of being limited to the first 20 rows.
        from .filtered_table import filtered_table
        filtered_table(
            pd.DataFrame(net_rows)[preview_cols],
            key="rules_net",
        )
    else:
        st.info("No network rules found in S3. Add providers in Settings → Provider Lists.")

    st.caption("Rules reload automatically on every scan cycle. "
               "Edit via Settings → Provider Lists.")


def _load_csv(store, key: str) -> list:
    """Read a CSV from S3, skip comment lines. Returns list of dicts."""
    try:
        raw = store.settings._get(key)
        if not raw:
            return []
        lines = [l for l in raw.decode().splitlines() if not l.startswith("#")]
        return pd.read_csv(io.StringIO("\n".join(lines))).to_dict("records")
    except Exception as e:
        log.warning("_load_csv(%s) failed: %s", key, e)
        return []


def _load_code_count(store) -> int:
    """Count non-comment rows in unauthorized_code.csv."""
    try:
        raw = store.settings._get("config/unauthorized_code.csv")
        if not raw:
            return 0
        lines = [l for l in raw.decode().splitlines()
                 if l.strip() and not l.startswith("#")]
        return max(0, len(lines) - 1)
    except Exception as e:
        log.warning("_load_code_count failed: %s", e)
        return 0
