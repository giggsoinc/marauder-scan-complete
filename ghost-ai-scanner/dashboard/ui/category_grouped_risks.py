# =============================================================
# FILE: dashboard/ui/category_grouped_risks.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Collapsible category-grouped view of open findings.
#          Replaces the row-soup. Each category is a parent row with
#          count + max-severity + last-seen. Expand to see per-signature
#          children. Bulk actions per category: Authorize, Suppress,
#          Show cleanup hint.
# DEPENDS: streamlit, services.authorize, cleanup_hints
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

import os
import sys
from collections import defaultdict

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from cleanup_hints   import cleanup_hint  # noqa: E402
from services.authorize import authorize  # noqa: E402


_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _max_sev(rows: list) -> str:
    out = "LOW"
    for r in rows:
        s = (r.get("severity") or "LOW").upper()
        if _SEV_RANK.get(s, 0) > _SEV_RANK.get(out, 0):
            out = s
    return out


def _group_by_category(rows: list) -> dict:
    out: dict = defaultdict(list)
    for r in rows:
        if r.get("status") == "resolved":
            continue
        out[r.get("category") or "unknown"].append(r)
    return out


def render_grouped_risks(rows: list, store=None, owner_email: str = "") -> None:
    """One section per category. Click to expand → per-signature rows.
    `store` is required for the Authorize button to write to S3;
    if None, button is hidden (read-only mode)."""
    groups = _group_by_category(rows)
    if not groups:
        st.info("No open findings. Clean posture.")
        return

    st.markdown(
        '<div class="card-title">OPEN FINDINGS — GROUPED</div>',
        unsafe_allow_html=True,
    )
    # Render sorted by severity then count.
    items = sorted(
        groups.items(),
        key=lambda kv: (-_SEV_RANK.get(_max_sev(kv[1]), 0), -len(kv[1])),
    )
    for cat, cat_rows in items:
        max_sev    = _max_sev(cat_rows)
        last_seen  = max(r.get("last_seen") or "" for r in cat_rows)
        header     = (f"{cat.replace('_', ' ').title()} — "
                      f"{len(cat_rows)} signature(s) · max sev {max_sev} · "
                      f"last seen {last_seen[:19] or '—'}")
        with st.expander(header, expanded=False):
            providers = sorted({r.get("provider", "") for r in cat_rows})
            for r in cat_rows[:50]:
                pname  = r.get("provider", "")
                occ    = r.get("occurrences", 1)
                fseen  = (r.get("first_seen") or "")[:19]
                lseen  = (r.get("last_seen")  or "")[:19]
                hint   = cleanup_hint(cat, r.get("os_name", ""))
                st.markdown(
                    f"<div style='font-family:JetBrains Mono;font-size:12px;"
                    f"padding:6px 0;border-bottom:1px solid #f3f4f6'>"
                    f"<b>{pname}</b> · {occ} occurrence(s) · "
                    f"{fseen} → {lseen}<br>"
                    f"<span style='color:#57606A'>💡 {hint}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            # Bulk Authorize for this category (only if store + email available)
            if store and owner_email:
                btn_key = f"auth_cat_{cat}_{owner_email}"
                if st.button(
                    f"✓ Authorize all {len(providers)} {cat.replace('_',' ')} provider(s) for {owner_email}",
                    key=btn_key,
                ):
                    total = authorize(store, owner_email, providers)
                    st.success(
                        f"Authorized {len(providers)} provider(s). "
                        f"User's allow-list now has {total} entries. "
                        "Agent picks up on next scan."
                    )
