# =============================================================
# FILE: dashboard/ui/manager_tab_inventory.py
# VERSION: 2.1.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Inventory tab — asset metrics, CrowdStrike banner, asset table.
#          v2: correct asset key (device_id > src_hostname > src_ip) and
#          owner attribution (email > owner) so each asset shows its real
#          user instead of collapsing to the last network event's owner.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v2.0.0  2026-04-27  Fix asset key + owner attribution for mixed
#                       network/endpoint event streams.
#   v2.1.0  2026-04-28  Add ?view=user_detail hyperlink on OWNER column.
# =============================================================

import os
from collections import defaultdict

import streamlit as st

from .helpers          import sev_badge
from .filtered_table   import search_box, apply_search_dicts
from .clickable_metric import clickable_metric, static_metric
from .drill_panel      import render_drill_panel

_PANEL = "mgr_inventory"

_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}


def _asset_key(e: dict) -> str:
    """Best identifier for grouping: device_id > src_hostname > src_ip."""
    return (e.get("device_id") or e.get("src_hostname") or
            e.get("src_ip") or "unknown")


def _owner_of(e: dict) -> str:
    """Authenticated identity: email (endpoint agent) > owner (network)."""
    return (e.get("email") or e.get("owner") or "").strip()


def render_inventory(events: list) -> None:
    """Asset summary KPIs, endpoint-protection banner, and asset table."""
    q = search_box("inventory", placeholder="search owner / IP / MAC …")
    if q:
        events = apply_search_dicts(events, q)

    keys = [_asset_key(e) for e in events]
    unique_keys = list(dict.fromkeys(keys))

    laptops = sum(1 for e in events if e.get("asset_type") == "laptop")
    ec2s    = sum(1 for e in events if e.get("asset_type") == "ec2")
    # Count assets that have at least one ENDPOINT_FINDING (actual outcome
    # for exploded scan findings — not ALERT which is the un-exploded summary).
    with_ai = len({_asset_key(e) for e in events
                   if e.get("outcome") == "ENDPOINT_FINDING"})

    c1, c2, c3, c4 = st.columns(4)
    static_metric(c1,    "Total Assets",    len(unique_keys))
    clickable_metric(c2, "Endpoints",       laptops,
                     panel_key=_PANEL, drill_field="asset_type",
                     drill_value="laptop", drill_label="Asset = laptop")
    clickable_metric(c3, "Cloud Instances", ec2s,
                     panel_key=_PANEL, drill_field="asset_type",
                     drill_value="ec2", drill_label="Asset = ec2")
    clickable_metric(c4, "With AI Events",  with_ai,
                     panel_key=_PANEL, drill_field="outcome",
                     drill_value="ENDPOINT_FINDING",
                     drill_label="Endpoint findings")
    render_drill_panel(_PANEL, events, limit=100)

    if not os.environ.get("CROWDSTRIKE_ENABLED", "false").lower() == "true":
        st.markdown(
            '<div style="background:rgba(210,153,34,.08);border:1px solid rgba(210,153,34,.3);'
            'border-radius:6px;padding:10px 16px;margin:12px 0;'
            'font-family:JetBrains Mono;font-size:11px;color:#9A6700;">'
            '⚠ Endpoint protection offline — process visibility limited. '
            'Showing network-layer attribution only.</div>',
            unsafe_allow_html=True,
        )

    # ── Build per-asset rows ──────────────────────────────────
    by_asset: dict = defaultdict(lambda: {
        "count": 0, "severity": "CLEAN",
        "owner": "", "dept": "", "mac": "", "type": "",
    })
    for e in events:
        key  = _asset_key(e)
        a    = by_asset[key]
        a["count"] += 1 if e.get("outcome") != "SUPPRESS" else 0

        # Owner: prefer authenticated email; only replace if current is blank
        new_owner = _owner_of(e)
        if new_owner and (not a["owner"] or e.get("email")):
            a["owner"] = new_owner

        if e.get("department"):
            a["dept"] = e["department"]
        if e.get("mac_address"):
            a["mac"] = e["mac_address"]
        if e.get("asset_type"):
            a["type"] = e["asset_type"]

        ev_sev  = (e.get("severity") or "CLEAN").upper()
        cur_sev = a["severity"]
        if _SEV_RANK.get(ev_sev, 0) > _SEV_RANK.get(cur_sev, 0):
            a["severity"] = ev_sev

    def _asset_row(key: str, v: dict) -> str:
        owner = v["owner"] or "—"
        # Link owner email to user detail page
        owner_cell = (
            f"<a href='?view=user_detail&email={owner}' "
            f"style='color:#0969DA;text-decoration:none'>{owner}</a>"
            if "@" in owner else owner
        )
        return (
            f"<tr>"
            f"<td style='font-family:JetBrains Mono;font-size:11px;color:#57606A'>"
            f"{key}</td>"
            f"<td>{v['type'] or '—'}</td>"
            f"<td>{owner_cell}</td>"
            f"<td>{v['dept'] or '—'}</td>"
            f"<td style='font-family:JetBrains Mono;font-size:10px;color:#57606A'>"
            f"{v['mac'] or '—'}</td>"
            f"<td style='text-align:center'>{v['count']}</td>"
            f"<td>{sev_badge(v['severity'] if v['count'] > 0 else 'CLEAN')}</td>"
            f"</tr>"
        )

    rows = "".join(
        _asset_row(key, v)
        for key, v in sorted(by_asset.items(),
                              key=lambda x: x[1]["count"], reverse=True)[:20]
    )
    st.markdown('<div class="card-title">ASSET INVENTORY</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"<table><thead><tr>"
        f"<th>SOURCE IP / DEVICE</th><th>TYPE</th><th>USER</th>"
        f"<th>DEPT</th><th>MAC</th><th>EVENTS</th><th>STATUS</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )
