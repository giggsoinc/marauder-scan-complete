# =============================================================
# FILE: src/store/summary_store.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Read and write pre-aggregated daily summary JSON.
#          Grafana dashboards read this for all charts — never raw findings.
#          Summarizer.py writes after each scan cycle.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: store.base_store
# =============================================================

import json
import logging
from datetime import date
from typing import Optional
from .base_store import BaseStore

log = logging.getLogger("marauder-scan.summary_store")


class SummaryStore(BaseStore):
    """Pre-aggregated daily stats. Dashboards read this not raw findings."""

    def _key(self, summary_date: str) -> str:
        return f"summary/daily/{summary_date}.json"

    def read(self, summary_date: Optional[str] = None) -> dict:
        """
        Read summary for a given date.
        Defaults to today if no date provided.
        Returns empty dict if no summary exists yet.
        """
        target = summary_date or date.today().isoformat()
        raw = self._get(self._key(target))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"Summary parse failed [{target}]: {e}")
            return {}

    def write(self, summary: dict, summary_date: Optional[str] = None) -> bool:
        """
        Write daily summary JSON to S3.
        Called by summarizer.py after every scan cycle.
        """
        target = summary_date or date.today().isoformat()
        summary["date"] = target
        ok = self._put(
            self._key(target),
            json.dumps(summary, indent=2).encode(),
            "application/json",
        )
        if ok:
            log.info(f"Summary written for {target}")
        return ok

    def read_range(self, days: int = 7) -> list:
        """
        Read summaries for the last N days.
        Returns list of summary dicts ordered newest first.
        Used by Grafana trend charts.
        """
        from datetime import timedelta
        summaries = []
        today = date.today()
        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            summary = self.read(d)
            if summary:
                summaries.append(summary)
        return summaries

    def list_available(self) -> list:
        """List all dates that have summaries in S3."""
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            dates = []
            for page in paginator.paginate(
                Bucket=self.bucket, Prefix="summary/daily/"
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Extract date from summary/daily/YYYY-MM-DD.json
                    filename = key.split("/")[-1]
                    if filename.endswith(".json"):
                        dates.append(filename.replace(".json", ""))
            return sorted(dates, reverse=True)
        except Exception as e:
            log.error(f"Failed to list summaries: {e}")
            return []
