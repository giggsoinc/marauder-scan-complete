# =============================================================
# FILE: dashboard/ui/reports/r1_exec.py
# VERSION: 1.0.0 / UPDATED: 2026-04-28 / OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: R1 — Executive Risk Summary HTML builder.
#          KPI row, top-5 users, top-5 providers, geo spread, risk verdict.
# AUDIT LOG: v1.0.0 2026-04-28 Initial.
# =============================================================

from collections import Counter, defaultdict
from . import _header


def _top5_users(evts: list) -> list:
    """Return top-5 (user, count, max_sev, last_seen) tuples by finding count."""
    counts: Counter = Counter()
    sev_map: dict = defaultdict(list)
    last_seen: dict = {}
    for e in evts:
        key = e.get("email") or e.get("owner") or "unknown"
        counts[key] += 1
        sev_map[key].append(e)
        ts = (e.get("timestamp") or "")[:10]
        if ts > last_seen.get(key, ""):
            last_seen[key] = ts
    rows = []
    for user, cnt in counts.most_common(5):
        rows.append((user, cnt, _header.max_sev(sev_map[user]), last_seen.get(user, "—")))
    return rows


def _top5_providers(evts: list) -> list:
    """Return top-5 (provider, category, count, max_sev) tuples by finding count."""
    counts: Counter = Counter()
    cat_map: dict = {}
    sev_map: dict = defaultdict(list)
    for e in evts:
        p = e.get("provider") or "unknown"
        counts[p] += 1
        cat_map[p] = e.get("category") or "—"
        sev_map[p].append(e)
    rows = []
    for prov, cnt in counts.most_common(5):
        rows.append((prov, cat_map[prov], cnt, _header.max_sev(sev_map[prov])))
    return rows


def _kpi_card(value: str, label: str, extra_cls: str = "") -> str:
    """Render a single KPI card div."""
    cls = f"kc {extra_cls}".strip()
    return (f'<div class="{cls}">'
            f'<div class="kv">{value}</div>'
            f'<div class="kl">{label}</div></div>')


def build_html(events: list, d_from: str, d_to: str,
               admin_email: str, company: str, logo_b64: str) -> str:
    """Build Executive Risk Summary HTML report string."""
    evts = _header.filter_by_date(events, d_from, d_to)
    evts = [e for e in evts if e.get("outcome") == "ENDPOINT_FINDING"]

    sev_counts: Counter = Counter(
        (e.get("severity") or "LOW").upper() for e in evts
    )
    crit = sev_counts.get("CRITICAL", 0)
    high = sev_counts.get("HIGH", 0)
    users = {e.get("email") or e.get("owner") for e in evts if e.get("email") or e.get("owner")}
    providers = {e.get("provider") for e in evts if e.get("provider")}
    countries = sorted({e.get("geo_country") or "" for e in evts} - {""})

    # --- Verdict ---
    if crit:
        verdict_cls = "gb"
        verdict = f"<strong>{crit} CRITICAL finding{'s' if crit != 1 else ''}</strong> require immediate action."
    elif high:
        verdict_cls = "vb"
        verdict = f"<strong>{high} HIGH finding{'s' if high != 1 else ''}</strong> warrant prompt review."
    else:
        verdict_cls = "ok"
        verdict = "No critical findings detected in this period."

    # --- KPI row ---
    kpi_row = (
        '<div class="kr">'
        + _kpi_card(str(len(evts)), "Total Findings")
        + _kpi_card(str(crit), "Critical", "crit" if crit else "")
        + _kpi_card(str(len(users)), "Unique Users")
        + _kpi_card(str(len(providers)), "Unique Providers")
        + "</div>"
    )

    # --- Top-5 users table ---
    user_rows = "".join(
        f"<tr><td>{u}</td><td>{c}</td><td>{_header.sev_tag(s)}</td><td>{ls}</td></tr>"
        for u, c, s, ls in _top5_users(evts)
    ) or "<tr><td colspan='4'>No findings</td></tr>"
    user_tbl = ("<table><tr><th>USER</th><th>FINDINGS</th>"
                "<th>MAX SEV</th><th>LAST SEEN</th></tr>" + user_rows + "</table>")

    # --- Top-5 providers table ---
    prov_rows = "".join(
        f"<tr><td>{p}</td><td>{cat}</td><td>{c}</td><td>{_header.sev_tag(s)}</td></tr>"
        for p, cat, c, s in _top5_providers(evts)
    ) or "<tr><td colspan='4'>No findings</td></tr>"
    prov_tbl = ("<table><tr><th>PROVIDER</th><th>CATEGORY</th>"
                "<th>FINDINGS</th><th>MAX SEV</th></tr>" + prov_rows + "</table>")

    geo = ", ".join(countries) if countries else "No geographic data available."

    body = (
        '<div class="sec"><div class="st">Risk Overview</div>'
        + kpi_row
        + f'<div class="{verdict_cls}">{verdict}</div></div>'
        + '<div class="sec"><div class="st">Top 5 Users by Findings</div>' + user_tbl + "</div>"
        + '<div class="sec"><div class="st">Top 5 Providers by Findings</div>' + prov_tbl + "</div>"
        + '<div class="sec"><div class="st">Geographic Spread</div>'
        + f'<p style="font-size:10px;margin:8px 0">{geo}</p></div>'
    )
    return _header.wrap_html(
        "Executive Risk Summary", body, company, d_from, d_to, admin_email, logo_b64
    )
