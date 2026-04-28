# =============================================================
# FILE: main.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Container entrypoint. Wires bootstrap and threads.
#          Watchdog restarts container if any thread dies.
# USAGE: python main.py
# =============================================================

import sys
import time
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("marauder-scan.main")

sys.path.insert(0, "src")

from bootstrap   import validate_env, build_store, load_settings, build_resolver, maybe_backfill, seed_config_files
from rule_health  import self_check_rules
from threads      import scanner_loop, alerter_backlog, url_refresh_loop, streamlit_proc


def main():
    log.info("PatronAI — Starting — Giggso Inc v1.2.0")

    validate_env()
    store    = build_store()
    seed_config_files(store)          # push bundled CSVs → S3 on every startup
    self_check_rules()                # validate merged rule counts; emit self-alert if low
    settings = load_settings(store)
    resolver = build_resolver(store, settings)
    maybe_backfill(store)

    stop = threading.Event()

    threads = [
        threading.Thread(target=scanner_loop,     args=(store, resolver, settings, stop), name="scanner",     daemon=True),
        threading.Thread(target=alerter_backlog,  args=(store, resolver, settings, stop), name="alerter",     daemon=True),
        threading.Thread(target=url_refresh_loop, args=(store, stop),                     name="url_refresh", daemon=True),
        threading.Thread(target=streamlit_proc,   args=(stop,),                           name="streamlit",   daemon=True),
    ]

    for t in threads:
        t.start()
        log.info(f"Started: {t.name}")

    try:
        while not stop.is_set():
            for t in threads:
                if not t.is_alive():
                    log.critical(f"Thread died: {t.name} — shutting down")
                    stop.set()
            time.sleep(5)
    except KeyboardInterrupt:
        log.info("Interrupt — shutting down")
        stop.set()

    for t in threads:
        t.join(timeout=10)
    log.info("Stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
