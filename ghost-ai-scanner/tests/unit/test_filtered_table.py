# =============================================================
# FILE: tests/unit/test_filtered_table.py
# PROJECT: PatronAI — Phase 1B
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the global-search filter contract:
#          - case-insensitive substring match
#          - matches any string column
#          - empty / blank query passes through untouched
#          - non-string columns are ignored
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1B.
# =============================================================

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard"))

pytest.importorskip("pandas")

from ui.filtered_table import _apply_global_search   # noqa: E402


def _df(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def test_blank_query_returns_df_untouched():
    df = _df([{"a": "alpha"}, {"a": "beta"}])
    out = _apply_global_search(df, "")
    assert len(out) == 2


def test_single_word_filters_string_column():
    df = _df([{"provider": "chatgpt.com"},
              {"provider": "claude.ai"},
              {"provider": "ollama"}])
    out = _apply_global_search(df, "claude")
    assert len(out) == 1


def test_match_is_case_insensitive():
    df = _df([{"provider": "ChatGPT"}, {"provider": "Claude"}])
    out = _apply_global_search(df, "CLAUDE")
    assert len(out) == 1


def test_substring_match_works():
    df = _df([{"host": "alice-mbp"}, {"host": "bob-laptop"}])
    out = _apply_global_search(df, "mbp")
    assert len(out) == 1


def test_match_across_any_column():
    """Match on 'alice' should hit row whose host OR email contains it."""
    df = _df([
        {"host": "alice-mbp", "email": "x@y.com"},
        {"host": "z-laptop",  "email": "alice@x.com"},
        {"host": "z-laptop",  "email": "bob@x.com"},
    ])
    out = _apply_global_search(df, "alice")
    assert len(out) == 2


def test_no_match_returns_empty():
    df = _df([{"a": "alpha"}, {"a": "beta"}])
    out = _apply_global_search(df, "zzzz-no-match")
    assert len(out) == 0


def test_numeric_column_ignored():
    """Searching for digits should NOT inadvertently match int columns."""
    df = _df([{"name": "alpha", "count": 100}, {"name": "beta", "count": 200}])
    out = _apply_global_search(df, "100")
    assert len(out) == 0


def test_handles_na_values():
    """NaN values must not crash the search."""
    import pandas as pd
    df = pd.DataFrame([{"a": "alpha"}, {"a": None}])
    out = _apply_global_search(df, "alpha")
    assert len(out) == 1


def test_filtered_table_under_loc_cap():
    body = (REPO / "dashboard" / "ui" / "filtered_table.py").read_text()
    assert len(body.splitlines()) <= 150
