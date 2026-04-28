# =============================================================
# FILE: src/reporter/data_builder.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Reads store and builds structured data dicts for each
#          report section. Separated from PDF generation so data
#          layer can be tested independently of ReportLab.
# DEPENDS: blob_index_store, polars
# =============================================================

import logging
from collections import defaultdict
from datetime    import date, timedelta

log = logging.getLogger("marauder-scan.reporter.data_builder")


def build_summary(store, days: int) -> dict:
    """Aggregate summaries across N days from summary store."""
    summaries = store.summary.read_range(days)
    total     = sum(s.get("total_events", 0) for s in summaries)
    by_sev    = {}
    sources   = set()
    providers = set()
    fired     = sum(s.get("alerts_fired", 0) for s in summaries)

    for s in summaries:
        for sev, cnt in s.get("by_severity", {}).items():
            by_sev[sev] = by_sev.get(sev, 0) + cnt
        sources.update(s.get("unique_sources", []))
        providers.update(s.get("unique_providers", []))

    return {
        "total_events":     total,
        "by_severity":      by_sev,
        "unique_sources":   len(sources),
        "unique_providers": len(providers),
        "alerts_fired":     fired,
    }


def build_offenders(store, days: int) -> list:
    """Build top offenders list from last N days of findings."""
    counts = defaultdict(lambda: {
        "count": 0, "providers": set(),
        "last_seen": "", "severity": "LOW", "owner": ""
    })
    today = date.today()
    for i in range(days):
        d  = (today - timedelta(days=i)).isoformat()
        df = store.findings.read(d, limit=1000)
        if df.is_empty():
            continue
        for row in df.iter_rows(named=True):
            key = row.get("src_ip", "unknown")
            counts[key]["count"] += 1
            counts[key]["providers"].add(row.get("provider", ""))
            counts[key]["last_seen"] = max(
                counts[key]["last_seen"], row.get("timestamp", "")
            )
            if row.get("severity") == "CRITICAL":
                counts[key]["severity"] = "CRITICAL"
            elif row.get("severity") == "HIGH" and counts[key]["severity"] != "CRITICAL":
                counts[key]["severity"] = "HIGH"
            counts[key]["owner"] = row.get("owner", key)

    return sorted(
        [{"src_ip": ip, "owner": v["owner"], "count": v["count"],
          "providers": ", ".join(v["providers"]),
          "last_seen": v["last_seen"], "severity": v["severity"]}
         for ip, v in counts.items()],
        key=lambda x: x["count"], reverse=True
    )


def build_providers(store, days: int) -> list:
    """Build provider breakdown from last N days."""
    counts = defaultdict(lambda: {
        "count": 0, "sources": set(), "last_seen": "", "category": ""
    })
    today = date.today()
    for i in range(days):
        d  = (today - timedelta(days=i)).isoformat()
        df = store.findings.read(d, limit=1000)
        if df.is_empty():
            continue
        for row in df.iter_rows(named=True):
            p = row.get("provider", "Unknown")
            counts[p]["count"] += 1
            counts[p]["sources"].add(row.get("src_ip", ""))
            counts[p]["last_seen"] = max(
                counts[p]["last_seen"], row.get("timestamp", "")
            )
            counts[p]["category"] = row.get("category", "")

    return sorted(
        [{"provider": p, "category": v["category"],
          "count": v["count"], "unique_sources": len(v["sources"]),
          "last_seen": v["last_seen"]}
         for p, v in counts.items()],
        key=lambda x: x["count"], reverse=True
    )


def build_events(store, target_date: str, limit: int = 200) -> list:
    """Read latest findings for event log section."""
    df = store.findings.read(target_date, limit=limit)
    if df.is_empty():
        return []
    return df.sort("timestamp", descending=True).to_dicts()
