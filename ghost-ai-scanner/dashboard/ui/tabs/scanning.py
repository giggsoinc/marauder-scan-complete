# =============================================================
# FILE: dashboard/ui/tabs/scanning.py
# VERSION: 1.1.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Scanning settings tab — interval, dedup, lookback, max files,
#          and Privacy (email hashing) toggle.
#          User-facing labels only. No env var names. Admin-only.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
#   v1.1.0  2026-04-19  Privacy section — hash_emails toggle (GDPR posture)
# =============================================================

import streamlit as st
from .. import audit as _audit


def render(store, email: str) -> None:
    """Scanning settings form — interval, dedup, lookback, max files, privacy."""
    settings = store.settings.read()
    scanner  = settings.get("scanner",  {})
    alerts   = settings.get("alerts",   {})
    privacy  = settings.get("privacy",  {})

    st.markdown("**Scanning**")
    c1, c2 = st.columns(2)
    with c1:
        scan_interval = st.number_input(
            "Scan cycle (seconds)",
            min_value=60, max_value=3600,
            value=int(scanner.get("scan_interval_secs", 300)),
            help="How often the scanner checks for new traffic data.",
        )
    with c2:
        dedup_window = st.number_input(
            "Dedup window (minutes)",
            min_value=5, max_value=1440,
            value=int(alerts.get("dedup_window_minutes", 60)),
            help="Suppress duplicate alerts within this window.",
        )

    c3, c4 = st.columns(2)
    with c3:
        max_files = st.number_input(
            "Max files per cycle",
            min_value=10, max_value=5000,
            value=int(scanner.get("max_files_per_cycle", 500)),
            help="Cap the number of log files processed per scan cycle.",
        )
    with c4:
        lookback = st.number_input(
            "Lookback window (hours)",
            min_value=1, max_value=168,
            value=int(scanner.get("lookback_hours", 24)),
            help="How far back the scanner searches on first boot or after a gap.",
        )

    st.markdown("---")
    st.markdown("**Privacy**")
    hash_emails = st.toggle(
        "Hash employee emails in alert payloads",
        value=bool(privacy.get("hash_emails", False)),
        help=(
            "When ON, owner and email fields in SNS and Trinity payloads are "
            "replaced with SHA-256 hashes before dispatch. "
            "Findings stored in S3 remain unhashed for investigation. "
            "Toggle supports GDPR data minimisation posture."
        ),
    )

    if st.button("Save — Scanning", type="primary"):
        old = {
            "scan_interval_secs":   scanner.get("scan_interval_secs",  300),
            "dedup_window_minutes": alerts.get("dedup_window_minutes",  60),
            "max_files_per_cycle":  scanner.get("max_files_per_cycle", 500),
            "lookback_hours":       scanner.get("lookback_hours",        24),
            "hash_emails":          privacy.get("hash_emails",         False),
        }
        settings.setdefault("scanner", {}).update({
            "scan_interval_secs":  scan_interval,
            "max_files_per_cycle": max_files,
            "lookback_hours":      lookback,
        })
        settings.setdefault("alerts",  {})["dedup_window_minutes"] = dedup_window
        settings.setdefault("privacy", {})["hash_emails"]          = hash_emails
        new = {
            "scan_interval_secs":   scan_interval,
            "dedup_window_minutes": dedup_window,
            "max_files_per_cycle":  max_files,
            "lookback_hours":       lookback,
            "hash_emails":          hash_emails,
        }
        try:
            ok = store.settings.write(settings, written_by=email)
            if ok:
                _audit.write_batch(email, {k: (old[k], new[k]) for k in old})
                st.success("Scanning settings saved. Active within one scan cycle.")
            else:
                st.error("Save failed — check tenant storage permissions.")
        except Exception as e:
            st.error(f"Save error: {e}")
