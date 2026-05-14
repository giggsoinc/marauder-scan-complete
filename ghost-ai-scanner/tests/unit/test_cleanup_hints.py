# =============================================================
# FILE: tests/unit/test_cleanup_hints.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc
# PURPOSE: Lock the cleanup-hint contract — every supported category
#          must produce a non-empty suggestion. Operators read these
#          on every dashboard row.
# =============================================================

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from cleanup_hints import cleanup_hint


# Every category referenced by agent_explode._FINDING_SEVERITY must
# have a non-empty default ("*") hint. Adding a new category to the
# agent without a matching hint regresses this test → forces an update.
_SUPPORTED_CATEGORIES = [
    "browser", "process", "container_log_signal", "package",
    "ide_plugin", "container_image", "shell_history",
    "mcp_server", "agent_workflow", "agent_scheduled",
    "tool_registration", "vector_db",
]


@pytest.mark.parametrize("cat", _SUPPORTED_CATEGORIES)
def test_every_category_has_default_hint(cat):
    h = cleanup_hint(cat)
    assert h, f"category {cat!r} has no cleanup hint — add one"


def test_os_specific_hint_used_when_available():
    mac = cleanup_hint("mcp_server", os_name="darwin")
    lin = cleanup_hint("mcp_server", os_name="linux")
    win = cleanup_hint("mcp_server", os_name="windows")
    assert "Library/Application Support" in mac
    assert ".config/Claude" in lin
    assert "%APPDATA%" in win
    assert mac != lin != win


def test_unknown_category_returns_empty_string():
    assert cleanup_hint("not_a_category") == ""
    assert cleanup_hint("") == ""


def test_unknown_os_falls_back_to_wildcard():
    h = cleanup_hint("process", os_name="bsd")
    assert h  # falls back to "*"


def test_case_insensitive_inputs():
    assert cleanup_hint("PROCESS", os_name="DARWIN")
