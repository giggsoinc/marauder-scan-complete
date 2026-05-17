# =============================================================
# FILE: src/jobs/findings_compact.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Background job — collapse raw findings/ into a deduped
#          findings_current/ view keyed on finding_signature.
#          One real-world condition (e.g. "Cursor running on this
#          MacBook") becomes one row with first_seen / last_seen /
#          occurrences, not N rows for N scan cycles.
#          Also auto-resolves stale signatures whose last_seen is
#          older than STALE_CYCLES * SCAN_INTERVAL_SECS.
# WHY:    Agent emits full state every 30 min. Without compaction the
#          dashboard shows 1020 "endpoints" for a 1-laptop fleet and
#          50 alerts from a single snapshot. Raw findings/ is kept
#          untouched for audit fidelity (Bruce's mandate); the
#          compacted view is what dashboard + chat read at query time.
# USAGE:  scheduler_loop(stop) — daemon thread, runs every 5 min.
#          One-shot: compact_window(start_iso, end_iso).
# DEPENDS: store.findings_store, store.base_store
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial. Ships with fix/dashboard-noise-drama-mode.
#   v1.1.0  2026-05-17  Wire signal_classifier.enrich_signal() — adds
#                       signal_class/reason/persistence_days/scan_frequency_pct.
# =============================================================

import json
import logging
import os
import time
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("marauder-scan.jobs.findings_compact")

# How often the compaction job runs. 5 min is sub-cycle (scanner runs
# at SCAN_INTERVAL_SECS=300 default), so the compacted view trails the
# raw findings by at most one cycle.
COMPACT_INTERVAL_S = int(os.environ.get("COMPACT_INTERVAL_S", "300"))

# A signature unseen for STALE_CYCLES consecutive scan cycles is
# auto-resolved. Default = 24 cycles × 30 min = 12 h. Configurable so
# operators can tighten or loosen the auto-close window.
STALE_CYCLES = int(os.environ.get("AUTO_RESOLVE_STALE_CYCLES", "24"))
SCAN_INTERVAL_S = int(os.environ.get("SCAN_INTERVAL_SECS", "300"))


def _today_iso() -> str:
    return date.today().isoformat()


def _current_key(day_iso: str) -> str:
    """findings_current/YYYY/MM/DD/by_signature.jsonl"""
    return f"findings_current/{day_iso.replace('-', '/')}/by_signature.jsonl"


def _parse_ts(value: str) -> Optional[datetime]:
    """Lenient ISO parse; returns None on garbage."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compact_day(store, day_iso: str) -> dict:
    """Read every raw finding for one UTC day, group by signature,
    write the deduped view to findings_current/.

    Returns counts so the scheduler can log a one-line summary.
    """
    if store is None:
        return {"raw_rows": 0, "signatures": 0, "auto_resolved": 0}

    raw_rows = 0
    by_sig: dict = defaultdict(lambda: {
        "first_seen": None, "last_seen": None, "occurrences": 0,
        "sample": None,
    })

    # Read all 4 severity files for the day; merge into one signature map.
    for sev in store.findings.SEVERITY_FILES:
        df = store.findings.read(target_date=day_iso, severity=sev, limit=10_000)
        if df.is_empty():
            continue
        for row in df.iter_rows(named=True):
            sig = row.get("finding_signature")
            if not sig:
                # Legacy rows pre-v2.2 didn't have a signature; skip them
                # gracefully — they'll roll off via the 24h compaction
                # window naturally.
                continue
            raw_rows += 1
            ts = _parse_ts(row.get("timestamp"))
            slot = by_sig[sig]
            slot["occurrences"] += 1
            if slot["first_seen"] is None or (ts and ts < slot["first_seen"]):
                slot["first_seen"] = ts
            if slot["last_seen"] is None or (ts and ts > slot["last_seen"]):
                slot["last_seen"] = ts
            if slot["sample"] is None:
                slot["sample"] = row

    # Auto-resolve any signature whose last_seen is older than the
    # stale threshold. Resolution is RECORDED on the compacted row
    # (resolved_by + resolved_reason) — raw findings/ never touched.
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STALE_CYCLES * SCAN_INTERVAL_S)
    auto_resolved = 0
    out_rows = []
    for sig, slot in by_sig.items():
        sample = dict(slot["sample"] or {})
        sample["finding_signature"] = sig
        sample["first_seen"]  = slot["first_seen"].isoformat() if slot["first_seen"] else None
        sample["last_seen"]   = slot["last_seen"].isoformat()  if slot["last_seen"]  else None
        sample["occurrences"] = slot["occurrences"]
        if slot["last_seen"] and slot["last_seen"] < cutoff:
            sample["status"]          = "resolved"
            sample["resolved_by"]     = "auto"
            sample["resolved_reason"] = f"not_seen_{STALE_CYCLES}_cycles"
            auto_resolved += 1
        else:
            sample["status"] = "open"
        out_rows.append(sample)

    # Signal classification — adds signal_class/reason/persistence_days/scan_frequency_pct
    try:
        from jobs.signal_classifier import enrich_signal
        out_rows = enrich_signal(out_rows)
    except Exception as exc:
        log.warning("signal_classifier unavailable: %s", exc)

    out_lines = [json.dumps(r) for r in out_rows]

    # Replace the day's compacted view in one atomic put — idempotent
    # by design, so re-running for the same day produces identical output.
    key  = _current_key(day_iso)
    body = ("\n".join(out_lines) + "\n").encode() if out_lines else b""
    try:
        store.findings._put(key, body, "application/x-ndjson")
    except Exception as exc:
        log.error("compact_day put failed for %s: %s", key, exc)

    summary = {"raw_rows": raw_rows, "signatures": len(by_sig),
               "auto_resolved": auto_resolved}
    log.info("compact %s: %s raw rows → %s signatures (%s auto-resolved)",
             day_iso, raw_rows, len(by_sig), auto_resolved)
    return summary


def compact_window(store, start_iso: str, end_iso: str) -> dict:
    """One-shot: compact every UTC day in [start_iso, end_iso] inclusive.
    Used by the catch-up path on startup, and by the operator CLI."""
    start = date.fromisoformat(start_iso)
    end   = date.fromisoformat(end_iso)
    if end < start:
        return {"days": 0, "raw_rows": 0, "signatures": 0, "auto_resolved": 0}
    totals = {"days": 0, "raw_rows": 0, "signatures": 0, "auto_resolved": 0}
    day = start
    while day <= end:
        result = compact_day(store, day.isoformat())
        totals["days"]          += 1
        totals["raw_rows"]      += result["raw_rows"]
        totals["signatures"]    += result["signatures"]
        totals["auto_resolved"] += result["auto_resolved"]
        day += timedelta(days=1)
    return totals


def scheduler_loop(store, stop: threading.Event) -> None:
    """Daemon thread target. Runs compact_day(today) every COMPACT_INTERVAL_S."""
    log.info("findings_compact scheduler started — interval=%ss stale_cycles=%s",
             COMPACT_INTERVAL_S, STALE_CYCLES)
    while not stop.is_set():
        t0 = time.time()
        try:
            compact_day(store, _today_iso())
        except Exception as exc:
            log.error("findings_compact cycle error: %s", exc, exc_info=True)
        stop.wait(timeout=max(0, COMPACT_INTERVAL_S - (time.time() - t0)))
    log.info("findings_compact scheduler stopped")
