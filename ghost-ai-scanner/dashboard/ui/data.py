# =============================================================
# FILE: dashboard/ui/data.py
# VERSION: 2.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Cached data loaders for the PatronAI dashboard.
#          Loads real S3 data only — no synthetic fallback.
#          Walks back 7 days for findings. Returns empty state
#          when S3 is unavailable or bucket not configured.
#          Role-scoped: exec users see only their own events.
# DEPENDS: blob_index_store, MARAUDER_SCAN_BUCKET env var
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — extracted from ghost_dashboard.py
#   v1.1.0  2026-04-19  7-day lookback, full stderr logging
#   v2.0.0  2026-04-20  Remove synthetic demo fallback — real data only
#   v2.1.0  2026-04-27  Role-scoped: exec → filtered to own email only.
# =============================================================

import os
import sys
import logging
from datetime import date, timedelta

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

log = logging.getLogger("patronai.ui.data")

BUCKET: str = os.environ.get("MARAUDER_SCAN_BUCKET", "")
REGION: str = os.environ.get("AWS_REGION", "us-east-1")

_EMPTY_SUMMARY = {
    "total_events": 0, "critical_count": 0, "providers": [],
    "departments": [], "alerts_fired": 0, "built_at": "",
}

if not BUCKET:
    print("[data.py] WARNING: MARAUDER_SCAN_BUCKET not set.", file=sys.stderr)


@st.cache_data(ttl=60)
def load_data(email: str = "", role: str = "") -> tuple:
    """
    Return (events, summary). Both empty when S3 unavailable.
    Walks back up to 7 days for findings data.
    Role scoping: exec → filter events to caller's email only.
    """
    if not BUCKET:
        return [], _EMPTY_SUMMARY

    try:
        from blob_index_store import BlobIndexStore
        store   = BlobIndexStore(BUCKET, REGION)
        summary = store.summary.read() or _EMPTY_SUMMARY

        for days_back in range(0, 8):
            check_date = (date.today() - timedelta(days=days_back)).isoformat()
            try:
                df_raw = store.findings.read(check_date, limit=500)
            except Exception as exc:
                print(f"[data.py] findings.read({check_date}): {exc}", file=sys.stderr)
                continue
            if not df_raw.is_empty():
                events = df_raw.to_dicts()
                print(f"[data.py] {len(events)} events from {check_date}", file=sys.stderr)
                if role == "exec" and email:
                    em = email.lower()
                    events = [
                        e for e in events
                        if (e.get("owner", "") or "").lower() == em
                        or (e.get("email", "") or "").lower() == em
                    ]
                    print(f"[data.py] exec scope → {len(events)} for {email}",
                          file=sys.stderr)
                return events, summary

        print(f"[data.py] No findings in last 7 days for bucket={BUCKET}", file=sys.stderr)
        return [], summary

    except Exception as exc:
        print(f"[data.py] S3 load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return [], _EMPTY_SUMMARY


@st.cache_data(ttl=60)
def load_yesterday_summary() -> dict:
    """Yesterday's summary for delta calculations. Returns {} on error."""
    if not BUCKET:
        return {}
    try:
        from blob_index_store import BlobIndexStore
        store = BlobIndexStore(BUCKET, REGION)
        yest  = (date.today() - timedelta(days=1)).isoformat()
        return store.summary.read(yest) or {}
    except Exception as exc:
        log.debug("Yesterday summary unavailable: %s", exc)
        return {}


@st.cache_data(ttl=60)
def load_pipeline_state() -> dict:
    """Cursor state for pipeline health. Returns safe defaults on error."""
    if not BUCKET:
        return {"last_key": None, "last_processed_at": None,
                "files_processed": 0, "total_events": 0}
    try:
        from blob_index_store import BlobIndexStore
        return BlobIndexStore(BUCKET, REGION).cursor.read()
    except Exception as exc:
        log.debug("Pipeline state unavailable: %s", exc)
        return {"last_key": None, "last_processed_at": None,
                "files_processed": 0, "total_events": 0}
