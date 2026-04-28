# =============================================================
# FILE: src/summarizer/aggregator.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Aggregate a findings DataFrame into a summary dict.
#          Calls agg_helpers for each dimension.
#          Returns flat summary ready for summary_store.write().
# DEPENDS: summarizer.agg_helpers, polars
# =============================================================

import logging
from datetime import datetime, timezone

import polars as pl

from .agg_helpers import count_by, count_by_hour, top_sources

log = logging.getLogger("marauder-scan.summarizer.aggregator")


def aggregate(df: pl.DataFrame, target_date: str) -> dict:
    """
    Build summary dict from findings DataFrame.
    All aggregations delegated to agg_helpers.
    Returns dict written to summary/daily/{date}.json.
    """
    if df.is_empty():
        return _empty(target_date)

    by_outcome   = count_by(df, "outcome")
    by_severity  = count_by(df, "severity")
    by_provider  = count_by(df, "provider")
    by_dept      = count_by(df, "department")

    return {
        "date":             target_date,
        "built_at":         datetime.now(timezone.utc).isoformat(),
        "total_events":     len(df),
        "alerts_fired":     (
            by_outcome.get("DOMAIN_ALERT", 0)
            + by_outcome.get("PORT_ALERT", 0)
            + by_outcome.get("PERSONAL_KEY", 0)
        ),
        # Dashboard-friendly flat fields
        "critical_count":   by_severity.get("CRITICAL", 0),
        "providers":        sorted(by_provider.keys()),
        "departments":      sorted(by_dept.keys()),
        # Detailed breakdowns for charts
        "unique_sources":   df["src_ip"].n_unique() if "src_ip" in df.columns else 0,
        "unique_providers": df["provider"].n_unique() if "provider" in df.columns else 0,
        "by_severity":      by_severity,
        "by_provider":      by_provider,
        "by_department":    by_dept,
        "by_outcome":       by_outcome,
        "by_hour":          count_by_hour(df),
        "top_sources":      top_sources(df, n=10),
    }


def _empty(target_date: str) -> dict:
    """Empty summary template for days with no findings."""
    return {
        "date":             target_date,
        "built_at":         datetime.now(timezone.utc).isoformat(),
        "total_events":     0,
        "alerts_fired":     0,
        "critical_count":   0,
        "providers":        [],
        "departments":      [],
        "unique_sources":   0,
        "unique_providers": 0,
        "by_severity":      {},
        "by_provider":      {},
        "by_department":    {},
        "by_outcome":       {},
        "by_hour":          {},
        "top_sources":      [],
    }
