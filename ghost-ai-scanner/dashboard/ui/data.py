# =============================================================
# FILE: dashboard/ui/data.py
# VERSION: 2.2.0
# UPDATED: 2026-05-17
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
#   v2.2.0  2026-05-17  Read compacted view (findings_current/) first —
#                       has signal_class/persistence_days from classifier.
#                       Add load_ghost_events() + load_signal_events().
# =============================================================

import os
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
    log.warning("MARAUDER_SCAN_BUCKET not set")


@st.cache_data(ttl=60)
def load_data(email: str = "", role: str = "") -> tuple:
    """
    Return (events, summary). Both empty when S3 unavailable.
    Reads compacted view (findings_current/) first — has signal_class.
    Falls back to raw findings/ if compacted is empty.
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
                df = store.findings.read_compacted(check_date, limit=2000)
                if df.is_empty():
                    df = store.findings.read(check_date, limit=500)
            except Exception as exc:
                log.warning("findings read(%s): %s", check_date, exc)
                continue
            if not df.is_empty():
                events = df.to_dicts()
                log.debug("%d events from %s", len(events), check_date)
                if role == "exec" and email:
                    em = email.lower()
                    events = [
                        e for e in events
                        if (e.get("owner", "") or "").lower() == em
                        or (e.get("email", "") or "").lower() == em
                    ]
                    log.debug("exec scope → %d for %s", len(events), email)
                return events, summary

        log.debug("No findings in last 7 days for bucket=%s", BUCKET)
        return [], summary

    except Exception as exc:
        log.error("S3 load failed: %s: %s", type(exc).__name__, exc)
        return [], _EMPTY_SUMMARY


@st.cache_data(ttl=60)
def load_ghost_events(email: str = "", role: str = "") -> list:
    """Return only GHOST-classified events. Empty list when no data."""
    events, _ = load_data(email=email, role=role)
    return [e for e in events if e.get("signal_class") == "GHOST"]


@st.cache_data(ttl=60)
def load_signal_events(email: str = "", role: str = "") -> dict:
    """
    Return events grouped by signal_class.
    Keys: GHOST, NOISE, NO_ISSUE, UNCLASSIFIED (legacy rows without the field).
    """
    events, _ = load_data(email=email, role=role)
    buckets: dict[str, list] = {"GHOST": [], "NOISE": [], "NO_ISSUE": [], "UNCLASSIFIED": []}
    for e in events:
        sc = e.get("signal_class") or "UNCLASSIFIED"
        buckets.setdefault(sc, []).append(e)
    return buckets


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
