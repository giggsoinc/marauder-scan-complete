# =============================================================
# FILE: src/jobs/docs_refresh.py
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Background daemon that watches the product-docs directory
#          mtime and rebuilds the chat RAG index when anything has
#          changed. Cheap: a stat() loop over ~18 files, then a no-op
#          unless mtime advanced.
#
#          Wired into main.py as a daemon thread alongside scanner /
#          alerter / rollup_scheduler. Runs every DOCS_REFRESH_INTERVAL
#          seconds (default 300 = 5 min).
# =============================================================

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("marauder-scan.jobs.docs_refresh")

_DEFAULT_INTERVAL_S = 300


def docs_refresh_loop(stop_event: threading.Event,
                       interval_s: int = _DEFAULT_INTERVAL_S) -> None:
    """Run forever. Every interval_s seconds, ask the docs index to
    refresh. Idempotent — only rebuilds if a doc's mtime has advanced.

    Safe to start as a daemon thread. Catches and logs every error so
    a transient docs/ permission issue doesn't kill the thread (which
    would trip the watchdog and bounce the container).
    """
    interval = max(60, int(os.environ.get("DOCS_REFRESH_INTERVAL_S",
                                            interval_s)))
    log.info("docs_refresh_loop: starting (interval=%ds)", interval)

    # chat.docs_index is a sibling package of jobs/ (both under src/);
    # bootstrap.py / main.py ensure src/ is on sys.path before this loop runs.
    try:
        from chat.docs_index import get_index
    except Exception as exc:
        log.error("docs_refresh_loop: failed to import docs_index — "
                  "thread exiting (this disables auto-refresh; manual "
                  "refresh via chat 'refresh docs' still works): %s", exc)
        return

    # Trigger initial load on boot so the first chat query is fast.
    try:
        idx = get_index()
        st = idx.status()
        log.info("docs_refresh_loop: initial state — %d chunks across %d files",
                 st.get("chunks", 0), st.get("files", 0))
    except Exception as exc:
        log.warning("docs_refresh_loop: initial load failed (will retry): %s", exc)

    while not stop_event.is_set():
        if stop_event.wait(timeout=interval):
            return
        try:
            result = get_index().refresh()
            action = result.get("action")
            if action == "reindexed":
                log.info("docs_refresh_loop: reindexed — chunks %d→%d, files %d→%d",
                         result.get("chunks_before", 0),
                         result.get("chunks_after", 0),
                         result.get("files_before", 0),
                         result.get("files_after", 0))
            elif action in ("initial_load", "force_reload"):
                log.info("docs_refresh_loop: %s — %d chunks across %d files",
                         action, result.get("chunks", 0),
                         result.get("files", 0))
            # action == "no_change" → silent (the common case)
        except Exception as exc:
            log.warning("docs_refresh_loop: refresh failed (will retry): %s", exc)
