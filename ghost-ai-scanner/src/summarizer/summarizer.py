# =============================================================
# FILE: src/summarizer/summarizer.py
# VERSION: 1.0.1
# UPDATED: 2026-04-27
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Three-mode summarizer.
#          update_today() — called after every ingestor cycle.
#          run_now(date) — on-demand from Streamlit refresh button.
#          backfill(days) — rebuilds historical summaries on first deploy.
#          All three read findings via store, aggregate with Polars,
#          write summary JSON to S3. Grafana reads the summary not raw findings.
# DEPENDS: summarizer.aggregator, blob_index_store
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v1.0.1  2026-04-27  diagonal → diagonal_relaxed: agent scan columns (mcp_servers,
#                       tool_registrations, vector_dbs) are String in agent frames but
#                       Null in network frames — diagonal_relaxed coerces to supertype.
# =============================================================

import logging
import time
from datetime import date, timedelta
from typing   import Optional

import polars as pl

from .aggregator import aggregate

log = logging.getLogger("marauder-scan.summarizer")


class Summarizer:
    """
    Builds and writes daily summary JSONs from findings.
    Three modes: incremental, on-demand, backfill.
    """

    def __init__(self, store):
        # store: BlobIndexStore — reads findings, writes summary
        self._store = store

    def update_today(self) -> dict:
        """
        Incremental update — called after every ingestor cycle.
        Reads all of today's findings and rewrites today's summary.
        Fast — only reads today's files.
        Returns summary dict for logging.
        """
        today = date.today().isoformat()
        return self._build_and_write(today, mode="incremental")

    def run_now(self, target_date: Optional[str] = None) -> dict:
        """
        On-demand rebuild for a specific date.
        Called from Streamlit Refresh Now button or
        Streamlit ?action=refresh query param.
        Returns summary dict with build_duration_seconds.
        """
        target = target_date or date.today().isoformat()
        log.info(f"On-demand summary requested for {target}")
        return self._build_and_write(target, mode="on_demand")

    def backfill(self, days: int = 90) -> list:
        """
        Rebuild summaries for last N days.
        Called once on first deploy or when historical data is missing.
        Returns list of summary dicts — one per day.
        Skips dates where findings are empty.
        """
        log.info(f"Backfill starting — {days} days")
        results  = []
        today    = date.today()
        skipped  = 0

        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            result = self._build_and_write(d, mode="backfill")
            if result.get("total_events", 0) == 0:
                skipped += 1
            else:
                results.append(result)

        log.info(
            f"Backfill complete — {len(results)} days with data, "
            f"{skipped} empty days skipped"
        )
        return results

    # ── INTERNAL ──────────────────────────────────────────────

    def _build_and_write(self, target_date: str, mode: str = "incremental") -> dict:
        """
        Core logic. Read findings → aggregate → write summary.
        Returns summary dict with build metadata.
        """
        start = time.time()

        # Read all severity files for this date
        df = self._read_all_findings(target_date)

        # Aggregate using Polars
        summary = aggregate(df, target_date)

        # Stamp build metadata
        summary["build_mode"]             = mode
        summary["build_duration_seconds"] = round(time.time() - start, 3)

        # Write to S3 summary/daily/{date}.json
        ok = self._store.summary.write(summary, target_date)
        if ok:
            log.info(
                f"Summary [{mode}] {target_date}: "
                f"{summary['total_events']} events, "
                f"{summary['alerts_fired']} alerts — "
                f"{summary['build_duration_seconds']}s"
            )
        else:
            log.error(f"Failed to write summary for {target_date}")

        return summary

    def _read_all_findings(self, target_date: str) -> pl.DataFrame:
        """
        Read all severity partitions for a date into one DataFrame.
        Uses S3 Select push-down — only reads what exists.
        """
        severities = ["critical", "high", "medium", "unknown"]
        frames     = []

        for sev in severities:
            df = self._store.findings.read(
                target_date=target_date,
                severity=sev,
                limit=10000,   # higher limit for summarizer
            )
            if not df.is_empty():
                frames.append(df)

        if not frames:
            return pl.DataFrame()

        # Concatenate all severity frames
        try:
            return pl.concat(frames, how="diagonal_relaxed")
        except Exception as e:
            log.error(f"Failed to concat findings frames: {e}")
            return pl.DataFrame()
