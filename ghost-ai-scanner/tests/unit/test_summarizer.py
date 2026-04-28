# =============================================================
# FILE: tests/unit/test_summarizer.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Unit tests for Polars aggregation helpers.
#          No AWS calls. Tests agg_helpers functions directly.
# =============================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import polars as pl
from summarizer.agg_helpers import count_by, count_by_hour, top_sources
from summarizer.aggregator  import aggregate, _empty


def _sample_df():
    return pl.DataFrame({
        "src_ip":     ["10.0.0.1", "10.0.0.1", "10.0.0.2", "10.0.0.3"],
        "owner":      ["alice",    "alice",    "bob",      "charlie"],
        "department": ["Eng",      "Eng",      "Finance",  "Legal"],
        "provider":   ["OpenAI",   "OpenAI",   "HuggingFace", "OpenAI"],
        "severity":   ["HIGH",     "HIGH",     "CRITICAL", "LOW"],
        "outcome":    ["DOMAIN_ALERT", "DOMAIN_ALERT", "DOMAIN_ALERT", "SUPPRESS"],
        "timestamp":  ["2026-04-18T09:00:00Z", "2026-04-18T10:00:00Z",
                       "2026-04-18T09:30:00Z", "2026-04-18T14:00:00Z"],
    })


def test_count_by_severity():
    result = count_by(_sample_df(), "severity")
    assert result["HIGH"]     == 2
    assert result["CRITICAL"] == 1
    assert result["LOW"]      == 1


def test_count_by_provider():
    result = count_by(_sample_df(), "provider")
    assert result["OpenAI"]      == 3
    assert result["HuggingFace"] == 1


def test_count_by_missing_column():
    """Missing column returns empty dict — never raises."""
    result = count_by(_sample_df(), "nonexistent_column")
    assert result == {}


def test_count_by_hour_keys():
    result = count_by_hour(_sample_df())
    assert len(result) > 0
    # Keys should be hour prefixes
    for key in result:
        assert "T" in key  # ISO timestamp hour format


def test_top_sources_ranked():
    result = top_sources(_sample_df(), n=10)
    assert len(result) > 0
    # alice has 2 events — should be first
    assert result[0]["owner"] == "alice"
    assert result[0]["count"] == 2


def test_top_sources_respects_n():
    result = top_sources(_sample_df(), n=1)
    assert len(result) == 1


def test_aggregate_totals():
    df     = _sample_df()
    result = aggregate(df, "2026-04-18")
    assert result["total_events"]     == 4
    assert result["unique_sources"]   == 3
    assert result["unique_providers"] == 2
    assert result["date"]             == "2026-04-18"
    assert "built_at"                 in result


def test_aggregate_alerts_fired_excludes_suppress():
    df     = _sample_df()
    result = aggregate(df, "2026-04-18")
    # SUPPRESS outcome must not count as alert
    assert result["alerts_fired"] == 3  # 3 DOMAIN_ALERT, 1 SUPPRESS


def test_empty_df_returns_zeros():
    result = aggregate(pl.DataFrame(), "2026-04-18")
    assert result["total_events"]   == 0
    assert result["alerts_fired"]   == 0
    assert result["by_severity"]    == {}
    assert result["top_sources"]    == []
