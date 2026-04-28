# =============================================================
# FILE: tests/unit/test_tools_code_scan.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the tools-code scanner's contract:
#          - greps Python files inside DISCOVERED_REPOS for tool patterns
#          - counts only — never ships source lines
#          - skips vendored dirs (node_modules / .venv / __pycache__)
#          - LOC cap respected
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import os
import re
import json
from pathlib import Path

REPO  = Path(__file__).resolve().parents[2]
FRAGS = REPO / "agent" / "install"


def _run_tools_scan(home: Path, discovered_repos: list) -> list:
    """Exec redactor + tools_code scanner with synthetic DISCOVERED_REPOS."""
    ns: dict = {
        "re": re, "Path": Path, "os": os, "json": json,
        "subprocess": None,
        "OS_NAME": "darwin",
        "AGENT_DIR": home / ".patronai",
        "DISCOVERED_REPOS": discovered_repos,
    }
    real_home = Path.home
    Path.home = staticmethod(lambda: home)                       # type: ignore
    try:
        for frag in ("scan_redactor.py.frag", "scan_tools_code.py.frag"):
            exec(compile((FRAGS / frag).read_text(), frag, "exec"), ns)
        return ns["scan_tools_code"]()
    finally:
        Path.home = real_home                                    # type: ignore


def _make_repo(home: Path, name: str, files: dict) -> dict:
    """Create a fake repo dir with .git/ + files. Returns the dict shape
    that scan_repo_discovery would produce."""
    repo_root = home / name
    (repo_root / ".git").mkdir(parents=True)
    for relpath, body in files.items():
        p = repo_root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return {
        "path_safe":   "~/" + name,
        "name":        name,
        "head_sha":    "abc1234",
        "remote_host": "github.com",
    }


def test_no_repos_means_no_findings(tmp_path):
    assert _run_tools_scan(tmp_path, []) == []


def test_repo_with_no_tools_emits_nothing(tmp_path):
    r = _make_repo(tmp_path, "plain", {"main.py": "print('hi')"})
    assert _run_tools_scan(tmp_path, [r]) == []


def test_at_tool_decorator_detected(tmp_path):
    body = (
        "from langchain.tools import tool\n"
        "\n"
        "@tool\n"
        "def get_weather(city):\n"
        "    return 'sunny'\n"
    )
    r = _make_repo(tmp_path, "agent_repo", {"weather.py": body})
    out = _run_tools_scan(tmp_path, [r])
    assert len(out) == 1
    f = out[0]
    assert f["type"]              == "tool_registration"
    assert f["repo_name"]         == "agent_repo"
    assert f["total_tools"]       >= 1
    assert f["files_with_tools"]  == 1


def test_function_tool_decorator_detected(tmp_path):
    body = "@function_tool\ndef do(): pass\n"
    r = _make_repo(tmp_path, "ft_repo", {"a.py": body})
    out = _run_tools_scan(tmp_path, [r])
    assert any(f["repo_name"] == "ft_repo" for f in out)


def test_node_modules_is_skipped(tmp_path):
    """A repo whose only tool decorator is inside node_modules must NOT fire."""
    r = _make_repo(tmp_path, "x", {
        "node_modules/foo/agent.py": "@tool\ndef bad(): pass\n",
    })
    assert _run_tools_scan(tmp_path, [r]) == []


def test_venv_is_skipped(tmp_path):
    r = _make_repo(tmp_path, "x", {
        ".venv/lib/agent.py": "@tool\ndef bad(): pass\n",
    })
    assert _run_tools_scan(tmp_path, [r]) == []


def test_count_includes_multiple_decorators(tmp_path):
    body = "@tool\ndef a(): pass\n@tool\ndef b(): pass\n@function_tool\ndef c(): pass\n"
    r = _make_repo(tmp_path, "multi", {"tools.py": body})
    out = _run_tools_scan(tmp_path, [r])[0]
    assert out["total_tools"] >= 3


def test_per_file_lines_have_safe_paths(tmp_path):
    body = "@tool\ndef x(): pass\n"
    r = _make_repo(tmp_path, "p", {"deep/sub/y.py": body})
    f = _run_tools_scan(tmp_path, [r])[0]
    # File path inside per_file is relative to repo, no '/Users/' prefix.
    for entry in f["per_file"]:
        assert not entry["file_safe"].startswith("/")


def test_tools_scanner_under_loc_cap():
    body = (FRAGS / "scan_tools_code.py.frag").read_text()
    assert len(body.splitlines()) <= 150
