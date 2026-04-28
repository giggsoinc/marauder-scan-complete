# =============================================================
# FILE: src/store/findings_store.py
# VERSION: 1.0.1
# UPDATED: 2026-04-27
# PURPOSE: Write findings to partitioned JSONL files in S3.
#          Read findings back using S3 Select push-down filtering.
#          Polars for lazy dataframe construction — never loads full file.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: store.base_store, polars, boto3 S3 Select
# =============================================================

import json
import logging
from datetime import date
from typing import Optional
import polars as pl
from .base_store import BaseStore

log = logging.getLogger("marauder-scan.findings_store")


class FindingsStore(BaseStore):
    """Write and read findings partitioned by date and severity."""

    # Map severity labels to file names
    SEVERITY_FILES = ["critical", "high", "medium", "unknown"]

    def _key(self, finding_date: str, severity: str) -> str:
        """Build S3 key: findings/YYYY/MM/DD/{severity}.jsonl"""
        path = finding_date.replace("-", "/")
        return f"findings/{path}/{severity.lower()}.jsonl"

    def write(self, finding: dict) -> bool:
        """
        Append one finding to correct severity JSONL file.
        Read-modify-write pattern — findings files stay small per day per severity.
        """
        try:
            today = date.today().isoformat()
            severity = finding.get("severity", "unknown").lower()
            if severity not in self.SEVERITY_FILES:
                severity = "unknown"
            key = self._key(today, severity)

            # Read existing content — may not exist yet
            existing = self._get(key)
            new_line = (json.dumps(finding) + "\n").encode()
            ok = self._put(key, existing + new_line, "application/x-ndjson")
            if ok:
                log.debug(f"Finding written [{severity}]: {finding.get('event_id')}")
            return ok
        except Exception as e:
            log.error(f"Failed to write finding: {e}")
            return False

    def read(
        self,
        target_date: str,
        severity: Optional[str] = None,
        limit: int = 500,
        owner: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        Read findings for a date using S3 Select.
        Filters pushed to S3 — never loads full file into memory.
        Returns Polars DataFrame. Empty DataFrame on error or no data.
        """
        # Determine which severity files to read
        if severity and severity.upper() != "ALL":
            targets = [severity.lower()]
        else:
            targets = self.SEVERITY_FILES

        all_rows = []

        for sev in targets:
            key = self._key(target_date, sev)
            if not self._exists(key):
                continue

            # Build S3 Select SQL with optional filters
            conditions = []
            if owner:
                conditions.append(f"s.owner = '{owner}'")
            if provider:
                conditions.append(f"s.provider = '{provider}'")
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            expr = f"SELECT * FROM s3object s {where} LIMIT {limit}"

            try:
                resp = self.s3.select_object_content(
                    Bucket=self.bucket,
                    Key=key,
                    ExpressionType="SQL",
                    Expression=expr,
                    InputSerialization={
                        "JSON": {"Type": "LINES"},
                        "CompressionType": "NONE",
                    },
                    OutputSerialization={"JSON": {"RecordDelimiter": "\n"}},
                )
                for event in resp["Payload"]:
                    if "Records" in event:
                        chunk = event["Records"]["Payload"].decode()
                        for line in chunk.strip().split("\n"):
                            if line:
                                try:
                                    all_rows.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                log.warning(f"S3 Select failed for {key}: {e}")
                # Fallback: plain GetObject read
                try:
                    raw = self._get(key)
                    if raw:
                        rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
                        # Apply in-memory filters
                        if owner:
                            rows = [r for r in rows if r.get("owner") == owner]
                        if provider:
                            rows = [r for r in rows if r.get("provider") == provider]
                        all_rows.extend(rows[:limit])
                except Exception as e2:
                    log.warning(f"GetObject fallback also failed for {key}: {e2}")

        if not all_rows:
            return pl.DataFrame()

        # infer_schema_length=None: scan all rows before locking schema so
        # mixed network/endpoint events (different column types) don't crash.
        return pl.from_dicts(all_rows, infer_schema_length=None)

    def list_dates(self, prefix: str = "findings/") -> list:
        """List all dates that have findings in S3."""
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            dates = set()
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
                for cp in page.get("CommonPrefixes", []):
                    dates.add(cp["Prefix"])
            return sorted(dates, reverse=True)
        except Exception as e:
            log.error(f"Failed to list findings dates: {e}")
            return []
