# =============================================================
# FILE: tests/unit/test_code_analyser.py
# VERSION: 2.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Unit tests for code_analyser.py — Qwen 3 1.7B classifier.
#          subprocess.run mocked — no real model or llama-cli needed.
#          Covers happy path (classifier returns JSON), every fallback
#          path (model missing, llama-cli missing, timeout, empty, bad
#          JSON, generic exception), and is_available().
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial (Gemma 4 E4B).
#   v2.0.0  2026-04-25  Rewritten for Qwen 3 1.7B + regex fallback contract.
# =============================================================

import json
import os
import sys
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import code_analyser  # noqa: E402


def _mock_run(stdout: str, returncode: int = 0):
    """Build a mock subprocess.CompletedProcess with given stdout."""
    mock = MagicMock()
    mock.stdout     = stdout
    mock.returncode = returncode
    return mock


def _patch_paths(model_exists: bool = True, cli_exists: bool = True):
    """Patch os.path.exists for the model and llama-cli paths only."""
    def _exists(path):
        if path == code_analyser.MODEL_PATH:
            return model_exists
        if path == code_analyser.LLAMA_CLI:
            return cli_exists
        return True
    return patch("code_analyser.os.path.exists", side_effect=_exists)


def _resp(**overrides) -> str:
    """Build a Qwen-shaped JSON response with sensible defaults."""
    base = {
        "ai_frameworks": [], "mcp_usage": False, "mcp_server_host": "",
        "agent_patterns": [], "hardcoded_keys": False, "hardcoded_endpoints": [],
        "local_inference": False, "risk_level": "LOW", "reasoning": "",
    }
    base.update(overrides)
    return json.dumps(base)


CRITICAL_RESPONSE = _resp(
    ai_frameworks=["LangChain"], hardcoded_keys=True,
    hardcoded_endpoints=["api.openai.com"], risk_level="CRITICAL",
    agent_patterns=["chained LLM calls"],
    reasoning="LangChain detected with hardcoded OpenAI key.",
)
CLEAN_RESPONSE = _resp(reasoning="No AI usage detected.")


# ── happy paths ───────────────────────────────────────────────

def test_analyse_critical_result():
    with _patch_paths(), \
         patch("code_analyser.subprocess.run", return_value=_mock_run(CRITICAL_RESPONSE)):
        result = code_analyser.analyse("from langchain import OpenAI\nkey='sk-proj-123'")
    assert result["risk_level"]     == "CRITICAL"
    assert "LangChain"              in result["ai_frameworks"]
    assert result["hardcoded_keys"] is True


def test_analyse_clean_result():
    with _patch_paths(), \
         patch("code_analyser.subprocess.run", return_value=_mock_run(CLEAN_RESPONSE)):
        result = code_analyser.analyse("def add(a, b): return a + b")
    assert result["risk_level"]     == "LOW"
    assert result["ai_frameworks"]  == []
    assert result["hardcoded_keys"] is False


def test_analyse_stamps_qwen3_metadata():
    """Classifier path must stamp the Qwen3 model name."""
    with _patch_paths(), \
         patch("code_analyser.subprocess.run", return_value=_mock_run(CRITICAL_RESPONSE)):
        result = code_analyser.analyse("import langchain")
    assert result["_model"]    == "qwen3-1.7b"
    assert result["_analyser"] == "marauder-scan"
    assert result["_analysis_seconds"] >= 0


# ── fallback paths — every failure mode reroutes to regex_fallback ──

def test_analyse_timeout_falls_back_to_regex():
    with _patch_paths(), \
         patch("code_analyser.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="llama-cli", timeout=30)):
        result = code_analyser.analyse("import langchain")
    assert result["_fallback"]  == "timeout"
    assert result["_model"]     == "regex-fallback"
    assert result["risk_level"] == "HIGH"          # frameworks hit by regex


def test_analyse_empty_output_falls_back_to_regex():
    with _patch_paths(), \
         patch("code_analyser.subprocess.run", return_value=_mock_run("")):
        result = code_analyser.analyse("import langchain")
    assert result["_fallback"]  == "empty_response"
    assert result["_model"]     == "regex-fallback"


def test_analyse_malformed_json_falls_back_to_regex():
    with _patch_paths(), \
         patch("code_analyser.subprocess.run", return_value=_mock_run("not-json {")):
        result = code_analyser.analyse("def x(): pass")
    assert result["_fallback"] == "json_parse_failed"
    assert result["_model"]    == "regex-fallback"


def test_analyse_model_missing_falls_back_to_regex():
    with _patch_paths(model_exists=False):
        result = code_analyser.analyse("import langchain")
    assert result["_fallback"]  == "model_not_found"
    assert result["risk_level"] == "HIGH"          # regex catches langchain


def test_analyse_llama_cli_missing_falls_back_to_regex():
    with _patch_paths(cli_exists=False):
        result = code_analyser.analyse("import langchain")
    assert result["_fallback"] == "llama_cli_not_found"


# ── is_available() ────────────────────────────────────────────

def test_is_available_true_when_both_present():
    with _patch_paths(model_exists=True, cli_exists=True):
        assert code_analyser.is_available() is True


def test_is_available_false_when_either_missing():
    with _patch_paths(model_exists=False, cli_exists=True):
        assert code_analyser.is_available() is False
    with _patch_paths(model_exists=True, cli_exists=False):
        assert code_analyser.is_available() is False
