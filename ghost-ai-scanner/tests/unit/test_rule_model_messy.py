# =============================================================
# FILE: tests/unit/test_rule_model_messy.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Real-world messy CSV fixtures — proves the forgive-input
#          architecture absorbs paste-quality issues admins actually
#          ship from spreadsheets, Slack messages, and Word docs.
#          Pure-data, no AWS, no LocalStack.
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 6.5 — bulk-upload validation.
# =============================================================

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from matcher.rule_model import parse_csv_text, validate_rule, validate_code_rule  # noqa: E402


_HEADER_NET  = "name,category,domain,port,severity,notes"
_HEADER_CODE = "name,type,pattern,severity,notes"


def test_bom_and_smart_quotes_normalised():
    """UTF-8 BOM + curly quotes from Word both pass after parse_csv_text."""
    raw = (
        "\ufeff" + _HEADER_NET + "\n"
        '"OpenAI","LLM","\u201chttps://API.OpenAI.com/v1\u201d","443","high",\n'
    )
    clean, errors = parse_csv_text(raw, validate_rule)
    assert errors == []
    assert clean[0]["domain"] == "api.openai.com"
    assert clean[0]["severity"] == "HIGH"


def test_scheme_and_path_stripped():
    raw = _HEADER_NET + "\nFlowise,Visual,https://flowiseai.com/login,,HIGH,\n"
    clean, _ = parse_csv_text(raw, validate_rule)
    assert clean[0]["domain"] == "flowiseai.com"


def test_mixed_case_and_trailing_dot():
    raw = _HEADER_NET + "\nx,LLM,ChatGPT.COM.,443,HIGH,\n"
    clean, _ = parse_csv_text(raw, validate_rule)
    assert clean[0]["domain"] == "chatgpt.com"


def test_zero_width_chars_stripped():
    raw = _HEADER_NET + "\nx,LLM,\u200bclaude.ai\u200c,443,HIGH,\n"
    clean, _ = parse_csv_text(raw, validate_rule)
    assert clean[0]["domain"] == "claude.ai"


def test_blank_lines_skipped():
    raw = _HEADER_NET + "\n\nOK,LLM,api.openai.com,443,HIGH,\n\n"
    clean, errors = parse_csv_text(raw, validate_rule)
    assert len(clean) == 1
    assert errors == []


def test_comment_lines_ignored():
    raw = "# pasted from runbook\n" + _HEADER_NET + "\n# section: LLM\nA,LLM,api.openai.com,443,HIGH,\n"
    clean, _ = parse_csv_text(raw, validate_rule)
    assert len(clean) == 1


def test_severity_lowercase_and_typo_default_to_high():
    raw = _HEADER_NET + "\nA,LLM,api.openai.com,443,medium,\nB,LLM,api.anthropic.com,443,URGENT,\n"
    clean, _ = parse_csv_text(raw, validate_rule)
    sev = {r["domain"]: r["severity"] for r in clean}
    assert sev["api.openai.com"] == "MEDIUM"
    assert sev["api.anthropic.com"] == "HIGH"  # typo → default


def test_too_broad_rejected_with_line_no():
    raw = _HEADER_NET + "\nGood,LLM,api.openai.com,443,HIGH,\nBad,LLM,*.com,443,HIGH,\n"
    clean, errors = parse_csv_text(raw, validate_rule)
    assert len(clean) == 1
    assert len(errors) == 1
    assert errors[0]["line"] == 3
    assert "too broad" in errors[0]["reason"]


def test_port_oob_rejected():
    raw = _HEADER_NET + "\nx,LLM,api.openai.com,99999,HIGH,\n"
    _, errors = parse_csv_text(raw, validate_rule)
    assert len(errors) == 1
    assert "out of range" in errors[0]["reason"]


def test_code_pattern_lowered_on_parse():
    raw = _HEADER_CODE + "\nLangChain,framework,LangChain,HIGH,\n"
    clean, _ = parse_csv_text(raw, validate_code_rule)
    assert clean[0]["pattern"] == "langchain"


def test_partial_failure_returns_clean_subset():
    """One-bad-row-shouldn't-doom-the-batch invariant."""
    raw = (
        _HEADER_NET + "\n"
        "A,LLM,api.openai.com,443,HIGH,\n"
        "B,LLM,*.com,443,HIGH,\n"               # too broad
        "C,LLM,api.anthropic.com,443,HIGH,\n"
        "D,LLM,x.com,abc,HIGH,\n"               # bad port
        "E,LLM,claude.ai,443,HIGH,\n"
    )
    clean, errors = parse_csv_text(raw, validate_rule)
    assert len(clean) == 3
    assert len(errors) == 2
    assert {e["line"] for e in errors} == {3, 5}
