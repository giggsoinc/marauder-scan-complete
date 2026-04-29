# =============================================================
# FILE: dashboard/ui/chat/tools.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI chat — 8 pure analytics tool functions.
#          All accept a role-scoped events list as first arg.
#          Return JSON-serialisable dicts/lists. No Streamlit,
#          no LLM, no I/O — fully unit-testable standalone.
#          Schemas in tools_schema.py; engine dispatch in engine.py.
# DEPENDS: stdlib only
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

# ── Shared private helpers ─────────────────────────────────────

def _f(events):  return [e for e in events if e.get("outcome") == "ENDPOINT_FINDING"]
def _ts(e):      return e.get("timestamp") or e.get("ts") or ""
def _own(e):     return e.get("email") or e.get("owner") or "unknown"
_SEV = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ── Tool 1 ─────────────────────────────────────────────────────

def get_summary_stats(events: list) -> dict:
    """Overall posture: findings count, severity breakdown, users, providers."""
    f = _f(events)
    return {"total_findings": len(f), "total_events": len(events),
            "severities": dict(Counter(e.get("severity", "UNKNOWN") for e in f)),
            "unique_users": len({_own(e) for e in f}),
            "unique_providers": len({e.get("provider") for e in f
                                     if e.get("provider")})}


# ── Tool 2 ─────────────────────────────────────────────────────

def get_top_risky_users(events: list, n: int = 5) -> list:
    """Top N users by finding count with max severity per user."""
    counts: dict = defaultdict(int)
    sevs:   dict = defaultdict(set)
    for e in _f(events):
        u = _own(e); counts[u] += 1; sevs[u].add(e.get("severity", "LOW"))
    top = sorted(counts, key=lambda u: counts[u], reverse=True)[:n]
    return [{"user": u, "findings": counts[u],
             "max_severity": max(sevs[u], key=lambda s: _SEV.get(s, 0))}
            for u in top]


# ── Tool 3 ─────────────────────────────────────────────────────

def get_user_risk_profile(events: list, email: str) -> dict:
    """Full profile for one user: providers, devices, severities, categories."""
    ue = [e for e in events if _own(e) == email]
    f  = _f(ue)
    return {"user": email, "total_findings": len(f),
            "providers": sorted({e.get("provider") for e in ue if e.get("provider")}),
            "devices":   sorted({e.get("src_hostname") for e in ue if e.get("src_hostname")}),
            "severities": dict(Counter(e.get("severity", "UNKNOWN") for e in f)),
            "categories": dict(Counter(e.get("category", "unknown") for e in ue)),
            "latest": sorted([_ts(e) for e in f], reverse=True)[:3]}


# ── Tool 4 ─────────────────────────────────────────────────────
#
# SCALE UPGRADE → AWS Athena
# --------------------------
# Current: all events pre-loaded from S3 into memory; filtered here in Python.
# Scales to ~100k events. For multi-month history or millions of rows, replace
# the body of this function with a direct Athena query:
#
#   import boto3, time
#   athena = boto3.client("athena", region_name=os.environ["AWS_REGION"])
#   bucket = os.environ["MARAUDER_SCAN_BUCKET"]
#
#   where_clauses = []
#   if severity: where_clauses.append(f"severity = '{severity.upper()}'")
#   if user:     where_clauses.append(f"owner = '{user}'")
#   if category: where_clauses.append(f"category = '{category}'")
#   if d_from:   where_clauses.append(f"dt >= '{d_from}'")
#   if d_to:     where_clauses.append(f"dt <= '{d_to}'")
#   where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
#
#   sql = f"""
#       SELECT ts, owner, severity, category, provider, src_hostname
#       FROM patronai_findings
#       {where}
#       ORDER BY ts DESC
#       LIMIT {limit}
#   """
#
#   qid = athena.start_query_execution(
#       QueryString=sql,
#       QueryExecutionContext={"Database": "patronai"},
#       ResultConfiguration={"OutputLocation": f"s3://{bucket}/athena-results/"},
#   )["QueryExecutionId"]
#
#   # Poll until done (or raise on failure)
#   for _ in range(30):
#       state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
#       if state == "SUCCEEDED": break
#       if state in ("FAILED", "CANCELLED"): raise RuntimeError(f"Athena query {state}")
#       time.sleep(2)
#
#   rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
#   # rows[0] is the header row; rows[1:] are data rows
#   keys = [c["VarCharValue"] for c in rows[0]["Data"]]
#   return [dict(zip(keys, [c.get("VarCharValue","") for c in r["Data"]])) for r in rows[1:]]
#
# Athena table: Glue-catalogued external table over s3://{bucket}/findings/
# partitioned by year/month/day. Create with:
#   aws glue create-table ... (or add to prereqs.sh)
# The table name "patronai_findings" and database "patronai" are conventions —
# update to match whatever Glue catalog name you provision.

def query_findings(events: list, severity: str = "", user: str = "",
                   category: str = "", d_from: str = "",
                   d_to: str = "", limit: int = 20) -> list:
    """Filtered findings list, newest-first, capped at limit."""
    f = _f(events)
    if severity: f = [e for e in f if (e.get("severity") or "").upper() == severity.upper()]
    if user:     f = [e for e in f if _own(e) == user]
    if category: f = [e for e in f if e.get("category") == category]
    if d_from:   f = [e for e in f if _ts(e) >= d_from]
    if d_to:     f = [e for e in f if _ts(e) <= d_to + "T23:59:59"]
    return [{"ts": _ts(e), "user": _own(e), "severity": e.get("severity"),
             "category": e.get("category"), "provider": e.get("provider"),
             "device": e.get("src_hostname")}
            for e in sorted(f, key=_ts, reverse=True)[:limit]]


# ── Tool 5 ─────────────────────────────────────────────────────

def get_fleet_status(events: list) -> dict:
    """Heartbeat summary: total devices, silent (>24 h) hosts."""
    now = datetime.now(timezone.utc)
    latest: dict = {}
    for e in events:
        h = e.get("src_hostname") or ""
        if h and _ts(e) > latest.get(h, ""):
            latest[h] = _ts(e)
    silent = [h for h, t in latest.items()
              if t and (now - datetime.fromisoformat(
                  t.replace("Z", "+00:00"))).total_seconds() > 86400]
    return {"total_devices": len(latest), "silent_24h": len(silent),
            "silent_hosts": silent[:10], "latest_event": max(latest.values(), default="")}


# ── Tool 6 ─────────────────────────────────────────────────────

def get_shadow_ai_census(events: list) -> list:
    """Per-provider stats: unique users, devices, first/last seen."""
    p: dict = defaultdict(lambda: {"u": set(), "d": set(), "fi": "", "la": ""})
    for e in events:
        pv = e.get("provider") or ""
        if not pv: continue
        p[pv]["u"].add(_own(e)); p[pv]["d"].add(e.get("src_hostname") or "")
        t = _ts(e)
        if not p[pv]["fi"] or t < p[pv]["fi"]: p[pv]["fi"] = t
        if t > p[pv]["la"]: p[pv]["la"] = t
    return sorted([{"provider": pv, "users": len(v["u"]), "devices": len(v["d"]),
                    "first_seen": v["fi"], "last_seen": v["la"]}
                   for pv, v in p.items()],
                  key=lambda x: x["users"], reverse=True)


# ── Tool 7 ─────────────────────────────────────────────────────

def get_recent_activity(events: list, hours: int = 24) -> list:
    """Findings in the last N hours (default 24)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return query_findings(events, d_from=cutoff[:10], limit=50)


# ── Tool 8 ─────────────────────────────────────────────────────

def compare_periods(events: list, d1f: str, d1t: str,
                    d2f: str, d2t: str) -> dict:
    """Delta between two date ranges: finding count, new providers, new users."""
    def _s(df, dt): return [e for e in _f(events) if df <= _ts(e)[:10] <= dt]
    p1, p2 = _s(d1f, d1t), _s(d2f, d2t)
    return {"period_1": {"range": f"{d1f}→{d1t}", "findings": len(p1)},
            "period_2": {"range": f"{d2f}→{d2t}", "findings": len(p2)},
            "delta_findings": len(p2) - len(p1),
            "new_providers": sorted({e.get("provider") for e in p2}
                                    - {e.get("provider") for e in p1}),
            "new_users": sorted({_own(e) for e in p2} - {_own(e) for e in p1})}
