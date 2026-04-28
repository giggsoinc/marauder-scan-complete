# =============================================================
# FILE: src/store/settings_store.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Read and write config/settings.json from S3.
#          Streamlit writes. Scanner reads on every cycle.
#          First boot returns empty dict — scanner uses env defaults.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: store.base_store
# =============================================================

import json
import logging
from datetime import datetime, timezone
from .base_store import BaseStore

log = logging.getLogger("marauder-scan.settings_store")

SETTINGS_KEY = "config/settings.json"


class SettingsStore(BaseStore):
    """Read and write scanner settings persisted in S3."""

    def read(self) -> dict:
        """Pull settings.json from S3. Returns empty dict if not found.
        Guarantees ocsf_bucket is never an empty string — falls back to env.
        """
        import os
        raw = self._get(SETTINGS_KEY)
        if not raw:
            log.warning("settings.json not found. Using env defaults.")
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"settings.json parse failed: {e}")
            return {}
        # Prevent silent pipeline failure when ocsf_bucket was saved as ""
        bucket = data.get("storage", {}).get("ocsf_bucket", "")
        if not bucket:
            fallback = os.environ.get("MARAUDER_SCAN_BUCKET", "")
            if fallback:
                data.setdefault("storage", {})["ocsf_bucket"] = fallback
                log.warning("ocsf_bucket was empty — restored from env: %s", fallback)
        return data

    def write(self, settings: dict, written_by: str = "streamlit") -> bool:
        """
        Write settings.json to S3.
        Stamps last_written_by and last_written_at on every save.
        """
        try:
            # Stamp metadata before writing
            if "_meta" not in settings:
                settings["_meta"] = {}
            settings["_meta"]["last_written_by"] = written_by
            settings["_meta"]["last_written_at"] = (
                datetime.now(timezone.utc).isoformat()
            )
            body = json.dumps(settings, indent=2).encode()
            ok = self._put(SETTINGS_KEY, body, "application/json")
            if ok:
                log.info(f"settings.json saved by {written_by}")
            return ok
        except Exception as e:
            log.error(f"Failed to write settings: {e}")
            return False
