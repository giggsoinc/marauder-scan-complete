# =============================================================
# FILE: dashboard/ui/tabs/provider_lists.py
# VERSION: 2.2.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Provider Lists tab — orchestration only. Composes baseline
#          read-only views, custom editors (bulk-import + search +
#          clear + save), allow list, discovered-tools review queue,
#          and the audit tail. All heavy lifting lives in sibling
#          modules under tabs/.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial.
#   v2.0.0  2026-04-25  Group 6 — custom editors, conflict gate, banner, tail.
#   v2.1.0  2026-04-25  Group 6.5 — bulk import, search filter, clear button.
#   v2.2.0  2026-04-25  Group 2 — discovered AI tools review queue.
# =============================================================

import logging

import streamlit as st

from matcher.rule_model import (
    parse_csv_text, find_conflicts,
    validate_rule, validate_allow_rule, validate_code_rule,
)
from .. import audit_tail as _tail
from . import provider_lists_io     as _io
from . import provider_lists_import as _imp
from . import discovered_panel      as _disc

log = logging.getLogger("patronai.ui.provider_lists")

DENY_KEY              = "config/unauthorized.csv"
DENY_CUSTOM_KEY       = "config/unauthorized_custom.csv"
ALLOW_KEY             = "config/authorized.csv"
CODE_DENY_KEY         = "config/unauthorized_code.csv"
CODE_DENY_CUSTOM_KEY  = "config/unauthorized_code_custom.csv"
STATUS_KEY            = "config/load_status.json"

NET_COLS   = ["name", "category", "domain", "port", "severity", "notes"]
CODE_COLS  = ["name", "type", "pattern", "severity", "notes"]
ALLOW_COLS = ["name", "domain_pattern", "notes"]


def render(is_admin: bool, email: str = "") -> None:
    """Render the Provider Lists tab."""
    _io.render_status_banner(STATUS_KEY)

    st.markdown("**Network denylist — Baseline (Giggso-managed)**")
    with st.expander("Show baseline rules", expanded=False):
        _io.render_readonly_csv(DENY_KEY)
    st.divider()

    if is_admin:
        st.markdown("**Network denylist — Custom additions**")
        st.caption("Edit freely. Custom rows win on `(domain, port)` collision with baseline.")
        _custom_editor(email, DENY_CUSTOM_KEY, validate_rule, NET_COLS,
                       "denylist.network", dedup_keys=("domain", "port"))
        st.divider()

        st.markdown("**Code denylist — Custom additions**")
        st.caption("Patterns matched against committed code diffs (Marauder Scan layer).")
        _custom_editor(email, CODE_DENY_CUSTOM_KEY, validate_code_rule, CODE_COLS,
                       "denylist.code", dedup_keys=("pattern",))
        st.divider()

    st.markdown("**Allow list**")
    st.caption("Domains listed here suppress alerts.")
    _allow_editor(is_admin, email)
    st.divider()
    _disc.render(is_admin, email)
    st.divider()
    _tail.render(field_prefix="denylist", limit=5)


def _custom_editor(email: str, csv_key: str, validator, cols: list,
                   audit_field: str, dedup_keys: tuple) -> None:
    """Custom-deny editor: bulk-import → search filter → data_editor → Save / Clear."""
    _imp.render(csv_key, validator, cols, dedup_keys)
    df = _io.read_csv_df(csv_key, cols)
    _search_filter(df, csv_key)
    edited = st.data_editor(
        df, use_container_width=True, num_rows="dynamic",
        key=f"editor::{csv_key}",
        column_config={c: st.column_config.TextColumn(c) for c in cols},
    )
    c1, c2, _ = st.columns([1, 1, 4])
    save_clicked  = c1.button("Save",        key=f"save::{csv_key}",  type="primary")
    clear_clicked = c2.button("🗑 Clear",     key=f"clear::{csv_key}")
    if clear_clicked:
        _io.clear_cache(csv_key, cols)
        st.rerun()
    if not save_clicked:
        return
    raw = edited.to_csv(index=False)
    clean, errors = parse_csv_text(raw, validator)
    if errors:
        st.error(f"{len(errors)} row(s) invalid — fix and re-save.")
        import pandas as pd
        st.dataframe(pd.DataFrame(errors)[["line", "reason"]], hide_index=True)
        return
    conflicts = []
    if validator is validate_rule:
        allow_rows = _io.read_validated(ALLOW_KEY, validate_allow_rule)
        conflicts = find_conflicts(allow_rows, clean)
    if conflicts and not st.session_state.get(f"override::{csv_key}"):
        st.warning(
            f"{len(conflicts)} row(s) overlap your allow list — they will be suppressed at scan time."
        )
        st.button("Save anyway (override)", key=f"override::{csv_key}", on_click=lambda: None)
        return
    _io.put_csv(csv_key, raw, email, audit_field, len(df), len(clean), bool(conflicts))


def _search_filter(df, csv_key: str) -> None:
    """Display-only search: highlights rows that contain the typed substring."""
    q = st.text_input(
        "🔎 Find rows (display only — does not change the editor)",
        key=f"filter::{csv_key}", placeholder="Type a domain or name…",
    )
    if not q or df is None or len(df) == 0:
        return
    needle = q.lower().strip()
    mask = df.apply(lambda r: needle in " ".join(str(v).lower() for v in r.values), axis=1)
    matched = df[mask]
    st.caption(f"{len(matched)} match(es)")
    if len(matched):
        st.dataframe(matched, use_container_width=True, hide_index=True)


def _allow_editor(is_admin: bool, email: str) -> None:
    """Editable allow-list table; validates via validate_allow_rule on save."""
    df = _io.read_csv_df(ALLOW_KEY, ALLOW_COLS)
    if not is_admin:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", key="editor::allow")
    if not st.button("Save Allow list", type="primary", key="save::allow"):
        return
    raw = edited.to_csv(index=False)
    _, errors = parse_csv_text(raw, validate_allow_rule)
    if errors:
        st.error(f"{len(errors)} row(s) invalid — fix and re-save.")
        import pandas as pd
        st.dataframe(pd.DataFrame(errors)[["line", "reason"]], hide_index=True)
        return
    _io.put_csv(ALLOW_KEY, raw, email, "allow_list", len(df), len(edited), False)
