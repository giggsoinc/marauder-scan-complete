# =============================================================
# FILE: tests/unit/test_vector_dbs_scan.py
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the vector-DB scanner's contract:
#          - finds chroma.sqlite3 / .faiss / .lance files in home caches
#          - finds the same inside DISCOVERED_REPOS
#          - tags `source` correctly (home_cache vs repo)
#          - skips vendored dirs
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


def _run_vdb_scan(home: Path, discovered_repos: list = None) -> list:
    """Exec redactor + vector_dbs scanner under fake $HOME."""
    ns: dict = {
        "re": re, "Path": Path, "os": os, "json": json,
        "subprocess": None,
        "OS_NAME": "darwin",
        "AGENT_DIR": home / ".patronai",
        "DISCOVERED_REPOS": discovered_repos or [],
    }
    real_home = Path.home
    Path.home = staticmethod(lambda: home)                       # type: ignore
    try:
        for frag in ("scan_redactor.py.frag", "scan_vector_dbs.py.frag"):
            exec(compile((FRAGS / frag).read_text(), frag, "exec"), ns)
        return ns["scan_vector_dbs"]()
    finally:
        Path.home = real_home                                    # type: ignore


def _make_repo(home: Path, name: str, files: dict) -> dict:
    repo_root = home / name
    (repo_root / ".git").mkdir(parents=True)
    for relpath, body in files.items():
        p = repo_root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        if body is None:
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.write_text(body if isinstance(body, str) else "")
    return {
        "path_safe":   "~/" + name,
        "name":        name,
        "head_sha":    "abc1234",
        "remote_host": "github.com",
    }


def test_empty_home_no_findings(tmp_path):
    assert _run_vdb_scan(tmp_path) == []


def test_chroma_sqlite_in_home_cache_detected(tmp_path):
    chroma_dir = tmp_path / ".chroma"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_bytes(b"x")
    out = _run_vdb_scan(tmp_path)
    assert any(f["kind"] == "chroma" and f["source"] == "home_cache" for f in out)


def test_lancedb_extension_in_repo_detected(tmp_path):
    r = _make_repo(tmp_path, "rag_repo", {"data/embeddings.lance": "x"})
    out = _run_vdb_scan(tmp_path, [r])
    repo_finds = [f for f in out if f.get("source") == "repo"]
    assert any(f["kind"] == "lancedb" and f.get("repo_name") == "rag_repo"
               for f in repo_finds)


def test_faiss_extension_in_repo_detected(tmp_path):
    r = _make_repo(tmp_path, "rag", {"index.faiss": "x"})
    out = _run_vdb_scan(tmp_path, [r])
    assert any(f["kind"] == "faiss" for f in out)


def test_node_modules_is_skipped(tmp_path):
    """Vector files inside node_modules must NOT be reported."""
    r = _make_repo(tmp_path, "x", {"node_modules/lib/index.faiss": "x"})
    assert _run_vdb_scan(tmp_path, [r]) == []


def test_venv_is_skipped(tmp_path):
    r = _make_repo(tmp_path, "x", {".venv/lib/store.lance": "x"})
    assert _run_vdb_scan(tmp_path, [r]) == []


def test_path_is_redacted(tmp_path):
    r = _make_repo(tmp_path, "p", {"index.faiss": "x"})
    f = _run_vdb_scan(tmp_path, [r])[0]
    # path_safe must start with `~` (home redaction applied)
    assert f["path_safe"].startswith("~"), f["path_safe"]


def test_unrelated_files_are_skipped(tmp_path):
    r = _make_repo(tmp_path, "p", {"README.md": "hi"})
    assert _run_vdb_scan(tmp_path, [r]) == []


def test_vector_dbs_scanner_under_loc_cap():
    body = (FRAGS / "scan_vector_dbs.py.frag").read_text()
    assert len(body.splitlines()) <= 150
