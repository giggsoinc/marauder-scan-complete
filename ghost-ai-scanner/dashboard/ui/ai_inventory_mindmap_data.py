# =============================================================
# FILE: dashboard/ui/ai_inventory_mindmap_data.py
# PROJECT: PatronAI — Mega-PR
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Pure-data helpers for the AI Inventory mind map.
#          _build_graph  — turns deduped events into nodes + edges + metadata
#          _radial_pos   — computes (x, y) for each node in a radial tree
#          Both are Streamlit-free and unit-testable.
# DEPENDS: stdlib only (math, collections)
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial. Split from ai_inventory_mindmap.py.
# =============================================================

import math
from collections import defaultdict

from .manager_tab_ai_inventory_data import CATEGORY_LABELS

ROOT = "AI Assets"
_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}


def _radial_pos(ocp: dict) -> dict:
    """Custom radial tree layout.
    ocp: {owner: {cat_key: [prov_keys]}}
    Returns {node_label: (x, y)}."""
    pos    = {ROOT: (0.0, 0.0)}
    owners = list(ocp.keys())
    n_own  = max(len(owners), 1)

    for oi, owner in enumerate(owners):
        oa = 2 * math.pi * oi / n_own
        pos[owner] = (1.6 * math.cos(oa), 1.6 * math.sin(oa))

        cats   = list(ocp[owner].keys())
        n_cats = max(len(cats), 1)
        spread_c = min(math.pi * 0.7, math.pi * 0.7 / n_own * n_cats)

        for ci, cat in enumerate(cats):
            ca = oa if n_cats == 1 else (
                oa + spread_c * (ci - (n_cats - 1) / 2) / (n_cats - 1))
            pos[cat] = (2.9 * math.cos(ca), 2.9 * math.sin(ca))

            provs   = ocp[owner][cat]
            n_provs = max(len(provs), 1)
            spread_p = min(math.pi * 0.4, math.pi * 0.4 / n_cats * n_provs)

            for pi, prov in enumerate(provs):
                pa = ca if n_provs == 1 else (
                    ca + spread_p * (pi - (n_provs - 1) / 2) / (n_provs - 1))
                pos[prov] = (4.4 * math.cos(pa), 4.4 * math.sin(pa))
    return pos


def build_graph(events: list) -> tuple:
    """Build mind-map graph from deduped events.
    Returns (ocp, edges, meta, node_labels).
      ocp   : {owner: {cat_key: [prov_keys]}}
      edges : list of (from, to) node label pairs
      meta  : {node_label: {level, severity, raw_owner, raw_cat}}
      node_labels : ordered list — index matches Plotly point_index."""
    ocp:  dict = defaultdict(lambda: defaultdict(list))
    meta: dict = {ROOT: {"level": 0, "severity": "CLEAN"}}

    for e in events:
        owner = (e.get("email") or e.get("owner") or "(unattached)")[:30]
        cat   = CATEGORY_LABELS.get(e.get("category", ""), e.get("category", ""))
        prov  = (e.get("provider") or "unknown")[:35]
        sev   = (e.get("severity") or "LOW").upper()
        # Unique keys per owner/cat to avoid label collision
        cat_key  = f"{cat}\n[{owner[:12]}]"
        prov_key = f"{prov}\n({owner[:12]})"

        for key, lv, raw_c in [(owner, 1, ""), (cat_key, 2, e.get("category", ""))]:
            if key not in meta:
                meta[key] = {"level": lv, "severity": sev,
                             "raw_owner": owner, "raw_cat": raw_c}
            elif _SEV_RANK.get(sev, 0) > _SEV_RANK.get(meta[key]["severity"], 0):
                meta[key]["severity"] = sev

        if prov_key not in meta:
            meta[prov_key] = {"level": 3, "severity": sev,
                              "raw_owner": owner, "raw_cat": e.get("category", "")}
        if prov_key not in ocp[owner][cat_key]:
            ocp[owner][cat_key].append(prov_key)

    ocp_d = {o: dict(c) for o, c in ocp.items()}
    edges = (
        [(ROOT, o) for o in ocp_d]
        + [(o, c) for o, cats in ocp_d.items() for c in cats]
        + [(c, p) for cats in ocp_d.values() for c, provs in cats.items()
           for p in provs]
    )
    node_labels = [ROOT] + [n for n in meta if n != ROOT]
    return ocp_d, edges, meta, node_labels
