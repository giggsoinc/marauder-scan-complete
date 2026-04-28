# =============================================================
# FILE: src/store/cursor_store.py
# VERSION: 2.0.0
# UPDATED: 2026-04-26
# PURPOSE: Track scanner progress across cycles. As of v2.0.0 the cursor
#          is a LastModified TIMESTAMP, not an S3 key, so files that get
#          overwritten in place (heartbeats, scans → latest.json) get
#          re-read on every cycle. The previous key-cursor design only
#          ever read each file once — the dashboard was empty as a result.
# OWNER: Ravi Venugopal, Giggso Inc
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial — key-based cursor.
#   v2.0.0  2026-04-26  Added cursor_ts (LastModified-based). Backwards-compat
#                       read of legacy cursors (treats `last_processed_at`
#                       minus 1 hour as the seed cursor_ts so the dashboard
#                       fills with the last hour of data on first migration).
# DEPENDS: store.base_store
# =============================================================

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .base_store import BaseStore

log = logging.getLogger("marauder-scan.cursor_store")

CURSOR_KEY = "cursor/state.json"
_DEFAULT = {
    "cursor_ts":         None,
    "last_key":          None,
    "last_processed_at": None,
    "files_processed":   0,
    "total_events":      0,
}


class CursorStore(BaseStore):
    """Track scan position across container restarts."""

    def read(self) -> dict:
        """
        Read cursor state. Returns safe defaults on first run.
        cursor_ts=None tells ingestor to scan everything matching the prefix.
        Legacy cursors (no cursor_ts) get migrated in-place: cursor_ts
        becomes last_processed_at - 1h so the dashboard back-fills the
        last hour of data on the first cycle after upgrade.
        """
        raw = self._get(CURSOR_KEY)
        if not raw:
            log.info("No cursor found. First run — scanning from prefix start.")
            return dict(_DEFAULT)
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Cursor file corrupt. Resetting.")
            return dict(_DEFAULT)
        # Legacy migration — cursor_ts missing → seed from last_processed_at - 1 h
        if state.get("cursor_ts") is None and state.get("last_processed_at"):
            try:
                lpa = datetime.fromisoformat(state["last_processed_at"])
                seed = (lpa - timedelta(hours=1)).isoformat()
                state["cursor_ts"] = seed
                log.info(f"Cursor migrated to v2 — seeded cursor_ts={seed}")
            except Exception as e:
                log.warning(f"Could not parse legacy last_processed_at: {e}")
        return {**_DEFAULT, **state}

    def write(
        self,
        cursor_ts:       Optional[datetime],
        last_key:        str,
        files_processed: int,
        total_events:    int = 0,
    ) -> bool:
        """Persist the new cursor after a successful cycle."""
        state = {
            "cursor_ts":         cursor_ts.isoformat() if cursor_ts else None,
            "last_key":          last_key,
            "last_processed_at": datetime.now(timezone.utc).isoformat(),
            "files_processed":   files_processed,
            "total_events":      total_events,
        }
        ok = self._put(CURSOR_KEY, json.dumps(state).encode())
        if ok:
            log.debug(f"Cursor updated: cursor_ts={state['cursor_ts']} "
                      f"last_key={last_key} files={files_processed}")
        return ok

    def reset(self) -> bool:
        """Reset cursor to force full rescan from prefix start."""
        log.warning("Cursor reset requested. Full rescan on next cycle.")
        return self._put(CURSOR_KEY, json.dumps(dict(_DEFAULT)).encode())
