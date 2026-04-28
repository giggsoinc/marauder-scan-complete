# =============================================================
# FILE: src/ingestor/s3_walker.py
# VERSION: 2.0.0
# UPDATED: 2026-04-26
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: List and fetch new OCSF files from S3 since last cursor.
#          Handles gzip decompression and JSON line parsing.
#          Returns raw event dicts to the ingestor — no normalisation here.
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v1.0.1  2026-04-19  Multi-format extension support.
#   v2.0.0  2026-04-26  Cursor switched from key to LastModified timestamp.
#                       Without this, files that get OVERWRITTEN with the
#                       same key (heartbeats, scans → latest.json) were
#                       only ever read once — the entire dashboard was empty
#                       despite agents pushing data successfully.
#                       list_new_files() now returns (key, last_modified)
#                       tuples so the ingestor can advance the cursor on the
#                       max LastModified seen.
# DEPENDS: boto3, gzip, json
# =============================================================

import gzip
import json
import logging
from datetime import datetime, timezone
from typing import Generator, List, Optional, Tuple

import boto3

log = logging.getLogger("marauder-scan.ingestor.s3_walker")

_VALID_SUFFIXES = (".json", ".json.gz", ".jsonl", ".jsonl.gz", ".log.gz", ".log")


class S3Walker:
    """Walk S3 ocsf/ prefix; return objects modified after a cursor timestamp."""

    def __init__(self, bucket: str, region: str = "us-east-1"):
        self.bucket = bucket
        self.s3     = boto3.client("s3", region_name=region)

    def list_new_files(
        self,
        prefix: str                             = "ocsf/",
        after_ts: Optional[datetime]            = None,
        max_files: int                          = 100,
    ) -> List[Tuple[str, datetime]]:
        """
        Return objects modified after `after_ts`, oldest-first.
        Each item is (key, last_modified). Caller advances the cursor to
        max(last_modified) so the next call resumes correctly.
        """
        results: List[Tuple[str, datetime]] = []
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.lower().endswith(_VALID_SUFFIXES):
                        continue
                    lm = obj["LastModified"]
                    if lm.tzinfo is None:
                        lm = lm.replace(tzinfo=timezone.utc)
                    if after_ts is not None and lm <= after_ts:
                        continue
                    results.append((key, lm))
        except Exception as e:
            log.error(f"S3 list failed: {e}")
            return []

        # Sort oldest-first so the cursor advances monotonically.
        results.sort(key=lambda kv: kv[1])
        if len(results) > max_files:
            log.info(f"Capping at {max_files} of {len(results)} eligible files")
            results = results[:max_files]
        log.info(f"Found {len(results)} files modified after cursor")
        return results

    def read_events(self, key: str, source_hint: str = "") -> Generator:
        """
        Download one OCSF file from S3 and yield raw event dicts.
        Handles: .json (single event), .jsonl (JSON lines), .gz variants.
        Attaches source_hint so normalizer knows the format.
        """
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"].read()

            # Decompress if gzipped
            if key.endswith(".gz"):
                body = gzip.decompress(body)

            content = body.decode("utf-8", errors="replace")

            # Auto-detect source from key path
            hint = source_hint or _hint_from_key(key)

            # VPC Flow Logs are space-separated lines not JSON
            if hint == "vpc_flow":
                for line in content.splitlines():
                    if line.strip():
                        yield {"_raw": line, "_hint": hint}
                return

            # JSON lines format (one JSON object per line)
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    # Path hint takes priority; fall back to hint embedded in event
                    event["_hint"] = hint or event.get("_hint", "")
                    yield event
                except json.JSONDecodeError as e:
                    log.debug(f"JSON parse error in {key}: {e}")

        except Exception as e:
            log.error(f"Failed to read {key}: {e}")


def _hint_from_key(key: str) -> str:
    """Infer source hint from S3 key path segment."""
    key_lower = key.lower()
    if "packetbeat" in key_lower:
        return "packetbeat"
    if "zeek" in key_lower:
        return "zeek"
    if "vpc" in key_lower or "flow" in key_lower:
        return "vpc_flow"
    if "nac" in key_lower:
        return "nac_csv"
    if "agent" in key_lower:
        return "agent"
    return ""
