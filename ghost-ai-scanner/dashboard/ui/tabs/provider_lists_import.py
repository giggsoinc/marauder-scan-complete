# =============================================================
# FILE: dashboard/ui/tabs/provider_lists_import.py
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Bulk-import widget for the custom deny editors.
#          Drop a CSV → forgive-input normalisation via rule_model
#          → metrics card (valid · skipped) → issues table with
#          a Download issues CSV button → "Load N valid rows into
#          editor" button. Clean rows are appended + deduped to
#          the editor's session-state cache. No S3 writes here —
#          the existing Save flow on the parent page persists.
# DEPENDS: streamlit, pandas, matcher.rule_model
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 6.5 — bulk-import on-ramp.
# =============================================================

import io
import logging
from typing import Callable

import pandas as pd
import streamlit as st

from matcher.rule_model import parse_csv_text, dedupe

log = logging.getLogger("patronai.ui.provider_lists_import")


def render(csv_key: str, validator: Callable[[dict], dict],
           cols: list, dedup_keys: tuple) -> None:
    """
    Render a collapsible bulk-import expander.
    Loads cleaned rows into st.session_state[f"cache::{csv_key}"] when admin clicks load.
    """
    state_imported = f"imported::{csv_key}"
    state_errors   = f"import_errors::{csv_key}"
    cache_key      = f"cache::{csv_key}"
    upload_key     = f"upload::{csv_key}"

    with st.expander("📥 Bulk import from CSV", expanded=False):
        uploaded = st.file_uploader(
            "Drop a CSV — schemes, paths, quotes, casing all normalised on parse",
            type=["csv"], key=upload_key,
        )
        if uploaded is not None:
            _run_validation(uploaded, validator, state_imported, state_errors)

        clean = st.session_state.get(state_imported, [])
        errors = st.session_state.get(state_errors, [])

        if not clean and not errors:
            st.caption("No CSV uploaded yet. Headers must match the editor columns below.")
            return

        c1, c2 = st.columns(2)
        c1.metric("✓ Valid rows ready", len(clean))
        c2.metric("⚠ Rows skipped",     len(errors))

        if errors:
            with st.expander(f"Show {len(errors)} skipped rows", expanded=False):
                err_df = pd.DataFrame([
                    {"line": e["line"], "reason": e["reason"], **e.get("row", {})}
                    for e in errors
                ])
                st.dataframe(err_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download issues CSV", data=err_df.to_csv(index=False).encode(),
                    file_name=f"{csv_key.split('/')[-1].replace('.csv','')}-issues.csv",
                    mime="text/csv", key=f"dl::{csv_key}",
                )

        if clean and st.button(f"Load {len(clean)} valid rows into editor",
                               type="primary", key=f"load::{csv_key}"):
            _merge_into_cache(cache_key, clean, cols, dedup_keys)
            st.session_state[state_imported] = []
            st.session_state[state_errors] = []
            st.success(f"Loaded {len(clean)} rows. Edit below and click Save to persist.")
            st.rerun()


def _run_validation(uploaded, validator, state_imported: str, state_errors: str) -> None:
    """Read the uploaded file, parse via rule_model, persist results to session_state."""
    try:
        raw = uploaded.read().decode("utf-8-sig")  # tolerate BOM
    except Exception as exc:
        log.warning("upload decode failed: %s", exc)
        st.error("Could not read file as UTF-8. Re-export from your spreadsheet as CSV.")
        return
    clean, errors = parse_csv_text(raw, validator)
    st.session_state[state_imported] = clean
    st.session_state[state_errors]   = errors


def _merge_into_cache(cache_key: str, imported: list, cols: list, dedup_keys: tuple) -> None:
    """Append imported rows into the editor's session-state cache; dedupe with imported winning."""
    existing_df = st.session_state.get(cache_key, pd.DataFrame(columns=cols))
    existing = existing_df.to_dict("records") if len(existing_df) else []
    merged = dedupe(existing + imported, key_cols=dedup_keys)
    st.session_state[cache_key] = pd.DataFrame(merged, columns=cols)
