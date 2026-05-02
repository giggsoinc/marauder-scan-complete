# =============================================================
# FILE: main.py
# VERSION: 1.2.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc
# PURPOSE: Container entrypoint. Wires bootstrap and threads.
#          Watchdog restarts container if any thread dies.
# USAGE: python main.py
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v1.1.0  2026-04-29  Switch LLM to LFM2.5-1.2B-Thinking via --hf-repo.
#                       Remove curl download logic; llama-server handles it.
#                       LLAMA_CACHE=/models routes HF cache to named volume.
#   v1.2.0  2026-04-29  Hourly S3 rollup scheduler (per-user + per-tenant
#                       trees) + chat-history S3 lifecycle policy at startup.
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
from jobs.hourly_rollup import scheduler_loop as rollup_scheduler_loop
from jobs.docs_refresh  import docs_refresh_loop

_HF_REPO  = os.environ.get("LLM_MODEL_REPO", "LiquidAI/LFM2.5-1.2B-Thinking-GGUF")
_LLM_PORT = int(os.environ.get("LLM_SERVER_PORT", "8080"))
_ROLLUP_OFFSET_MIN = int(os.environ.get("ROLLUP_HOURLY_OFFSET_MINUTES", "5"))
_CHAT_RETENTION_DAYS = int(os.environ.get("CHAT_HISTORY_RETENTION_DAYS", "30"))


def _llama_server_thread() -> None:
    """Background daemon: run llama-server; downloads model from HuggingFace on first boot.

    Performance flags (added 2026-05-02 after measuring 10 tok/s CPU
    inference taking 60-150 sec per chat turn):
      --threads <all-cores>  : llama.cpp defaults to ~half cores; the
                                rest were idle. Empirically ~1.5× speedup
                                at 100% CPU during a turn.
      --predict <max>        : hard server-side cap on output tokens.
                                Belt-and-braces with the client-side
                                LLM_MAX_TOKENS so a runaway response
                                can't blow past N tokens even if a
                                client forgets to set max_tokens.
                                Default 384 (≤100-word answers + Sources
                                footer fit comfortably in 384 tokens).
    """
    threads = max(2, os.cpu_count() or 4)
    predict = int(os.environ.get("LLM_MAX_TOKENS", "384"))
    log.info("llama-server: starting on :%d — repo: %s — threads=%d predict=%d",
             _LLM_PORT, _HF_REPO, threads, predict)
    # LLAMA_CACHE=/models routes the HuggingFace download to the named Docker volume.
    subprocess.Popen(
        ["llama-server",
         "--hf-repo", _HF_REPO,
         "--port",    str(_LLM_PORT), "--host", "127.0.0.1",
         "--ctx-size", "8192",
         "--threads",  str(threads),
         "--predict",  str(predict)],
        stdout=subprocess.DEVNULL, stderr=None,
        env={**os.environ, "LLAMA_CACHE": "/models"},
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

    # Apply the chat-history lifecycle rule once per boot (idempotent).
    # chat.history lives in src/chat/ — sys.path already has src/.
    try:
        from chat.history import ensure_lifecycle_policy
        ensure_lifecycle_policy(_CHAT_RETENTION_DAYS)
    except Exception as exc:
        log.warning("ensure_lifecycle_policy failed (non-fatal): %s", exc)

    stop = threading.Event()

    # llama-server runs independently — downloads model on first boot then serves on :8080
    threading.Thread(target=_llama_server_thread, name="llama_server", daemon=True).start()
    log.info("Started: llama_server (background)")

    threads = [
        threading.Thread(target=scanner_loop,        args=(store, resolver, settings, stop), name="scanner",        daemon=True),
        threading.Thread(target=alerter_backlog,     args=(store, resolver, settings, stop), name="alerter",        daemon=True),
        threading.Thread(target=url_refresh_loop,    args=(store, stop),                     name="url_refresh",    daemon=True),
        threading.Thread(target=rollup_scheduler_loop, args=(stop, _ROLLUP_OFFSET_MIN),      name="rollup_scheduler", daemon=True),
        threading.Thread(target=docs_refresh_loop,   args=(stop,),                           name="docs_refresh",   daemon=True),
        threading.Thread(target=streamlit_proc,      args=(stop,),                           name="streamlit",      daemon=True),
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
