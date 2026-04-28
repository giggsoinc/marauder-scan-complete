# =============================================================
# FILE: src/store/dedup_store.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Alert deduplication. One alert per source IP per provider
#          per configurable time window. Prevents alert floods.
#          State persisted in S3 dedup/YYYY-MM-DD.json.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: store.base_store
# =============================================================

import json
import time
import logging
from datetime import date
from .base_store import BaseStore

log = logging.getLogger("marauder-scan.dedup_store")

DEFAULT_WINDOW_MINUTES = 60


class DedupStore(BaseStore):
    """
    Deduplication store. Checks whether an alert was recently fired
    for a given source IP and provider combination.
    Uses epoch timestamps so window check is a simple subtraction.
    """

    def _key(self) -> str:
        """Dedup file rotates daily."""
        return f"dedup/{date.today().isoformat()}.json"

    def _load(self) -> dict:
        """Load today's dedup records from S3."""
        raw = self._get(self._key())
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Dedup file corrupt. Starting fresh.")
            return {}

    def _save(self, records: dict) -> bool:
        """Persist dedup records to S3."""
        return self._put(self._key(), json.dumps(records).encode())

    def _entry_key(self, source_ip: str, provider: str) -> str:
        return f"{source_ip}::{provider}"

    def is_duplicate(
        self,
        source_ip: str,
        provider: str,
        window_minutes: int = DEFAULT_WINDOW_MINUTES,
    ) -> bool:
        """
        Returns True if this source+provider already alerted
        within the dedup window. False means fire the alert.
        """
        records = self._load()
        entry = self._entry_key(source_ip, provider)
        if entry not in records:
            return False
        elapsed_seconds = time.time() - records[entry]
        within_window = elapsed_seconds < (window_minutes * 60)
        if within_window:
            log.debug(f"Dedup suppressed: {entry} ({int(elapsed_seconds)}s ago)")
        return within_window

    def record(self, source_ip: str, provider: str) -> bool:
        """
        Record that an alert was fired for source+provider now.
        Call this immediately after dispatching the alert.
        """
        records = self._load()
        records[self._entry_key(source_ip, provider)] = time.time()
        ok = self._save(records)
        if ok:
            log.debug(f"Dedup recorded: {source_ip} → {provider}")
        return ok

    def clear(self, source_ip: str, provider: str) -> bool:
        """
        Remove a dedup entry to allow immediate re-alerting.
        Used when an incident is manually resolved and re-triggered.
        """
        records = self._load()
        entry = self._entry_key(source_ip, provider)
        if entry in records:
            del records[entry]
            log.info(f"Dedup cleared: {entry}")
            return self._save(records)
        return True

    def stats(self) -> dict:
        """Return dedup stats for the Streamlit settings dashboard."""
        records = self._load()
        now = time.time()
        return {
            "total_suppressed_today": len(records),
            "active_entries": [
                {
                    "key": k,
                    "last_alerted_seconds_ago": int(now - v),
                }
                for k, v in records.items()
            ],
        }
