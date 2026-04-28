# =============================================================
# FILE: src/summarizer/agg_helpers.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Pure Polars aggregation helper functions.
#          No S3 access. No side effects. Testable in isolation.
# DEPENDS: polars
# =============================================================

import logging
import polars as pl

log = logging.getLogger("marauder-scan.summarizer.agg_helpers")


def count_by(df: pl.DataFrame, col: str) -> dict:
    """Group by column — return {value: count} dict sorted by count desc."""
    if col not in df.columns:
        return {}
    try:
        result = (
            df.lazy()
            .filter(pl.col(col).is_not_null())
            .group_by(col)
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
            .collect()
        )
        return {
            str(row[col]): int(row["count"])
            for row in result.iter_rows(named=True)
            if row[col]
        }
    except Exception as e:
        log.debug(f"count_by [{col}] failed: {e}")
        return {}


def count_by_hour(df: pl.DataFrame) -> dict:
    """
    Bucket events by hour using timestamp prefix.
    Returns {YYYY-MM-DDTHH: count} for timeline chart.
    """
    if "timestamp" not in df.columns:
        return {}
    try:
        result = (
            df.lazy()
            .with_columns(pl.col("timestamp").str.slice(0, 13).alias("hour"))
            .group_by("hour")
            .agg(pl.len().alias("count"))
            .sort("hour")
            .collect()
        )
        return {str(r["hour"]): int(r["count"]) for r in result.iter_rows(named=True)}
    except Exception as e:
        log.debug(f"count_by_hour failed: {e}")
        return {}


def top_sources(df: pl.DataFrame, n: int = 10) -> list:
    """Return top N source IPs by event count with owner and department."""
    if "src_ip" not in df.columns:
        return []
    try:
        cols = [c for c in ["src_ip", "owner", "department"] if c in df.columns]
        result = (
            df.lazy()
            .group_by(cols)
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
            .limit(n)
            .collect()
        )
        return result.to_dicts()
    except Exception as e:
        log.debug(f"top_sources failed: {e}")
        return []
