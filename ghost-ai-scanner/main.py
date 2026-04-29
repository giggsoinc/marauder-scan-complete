# =============================================================
# FILE: main.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Container entrypoint. Wires bootstrap and threads.
#          Watchdog restarts container if any thread dies.
# USAGE: python main.py
# =============================================================

import glob
import os
import subprocess
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

_MODEL_REPO = os.environ.get("LLM_MODEL_REPO", "unsloth/Qwen3-0.6B-GGUF")
_MODEL_FILE = os.environ.get("LLM_MODEL_FILE", "Qwen3-0.6B-Q4_K_M.gguf")
_MODEL_PATH = os.environ.get("LLM_MODEL_PATH", f"/models/{_MODEL_FILE.lower()}")
_MODEL_URL  = os.environ.get("LLM_MODEL_URL",
    f"https://huggingface.co/{_MODEL_REPO}/resolve/main/{{_MODEL_FILE}}")
_LLM_PORT   = int(os.environ.get("LLM_SERVER_PORT", "8080"))


def _llama_server_thread() -> None:
    """Background daemon: download GGUF model via curl if absent, then run llama-server."""
    if not os.path.exists(_MODEL_PATH):
        url = _MODEL_URL.format(_MODEL_FILE=_MODEL_FILE)
        log.info("llama-server: model absent — downloading from %s (~1 GB, first boot)...", url)
        try:
            os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
            subprocess.run(
                ["curl", "-fsSL", "-o", _MODEL_PATH, url],
                check=True, timeout=7200,
            )
            log.info("llama-server: model ready at %s", _MODEL_PATH)
        except Exception as exc:
            log.warning("llama-server: model download failed (%s) — chat unavailable", exc)
            return

    log.info("llama-server: starting on :%d with %s", _LLM_PORT, _MODEL_PATH)
    subprocess.Popen(
        ["llama-server", "--model", _MODEL_PATH,
         "--port", str(_LLM_PORT), "--host", "127.0.0.1",
         "--ctx-size", "8192"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    log.info("llama-server: process launched on :%d", _LLM_PORT)


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

    # llama-server runs independently — downloads model on first boot then serves on :8080
    threading.Thread(target=_llama_server_thread, name="llama_server", daemon=True).start()
    log.info("Started: llama_server (background)")

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
