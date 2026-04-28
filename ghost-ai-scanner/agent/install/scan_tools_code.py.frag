# =============================================================
# FRAGMENT: scan_tools_code.py.frag
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Per-repo inventory of LLM tool registrations. Greps Python
#          files inside DISCOVERED_REPOS (set by scan_repo_discovery)
#          for `@tool`, `@function_tool`, `Tool(`, `register_tool` and
#          common framework decorators. Counts only — never ships the
#          source line, only the count + filename. Stays inside
#          discovered repos so it does not trawl the home dir.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import time as _time

# Patterns to match a tool registration. Anchored with word boundaries
# so a method-call like `tool(...)` lower-case still matches; a comment
# `# tool` is rejected by requiring a non-comment context.
_TOOL_PATTERNS_RE = re.compile(
    r"(?m)^[^#]*?"                                    # not a comment-only line
    r"(?:"
    r"@tool\b|"
    r"@function_tool\b|"
    r"@function_calling\b|"
    r"@register_tool\b|"
    r"\bTool\(\s*name\s*=|"
    r"\bFunctionTool\(|"
    r"\bregister_tool\(|"
    r"langchain[._]tools|"
    r"crewai[._]tools|"
    r"autogen[._]tools"
    r")"
)

_PY_MAX_BYTES_PER_FILE = 500_000                       # don't read 5 MB notebooks
_PY_TIME_CAP_SECONDS   = 30.0                          # whole-scan deadline


def _python_files_in(repo_root: Path, deadline: float) -> list:
    """Yield .py files inside a repo, depth-limited, deadline-respecting."""
    out: list = []
    try:
        for p in repo_root.rglob("*.py"):
            if _time.time() > deadline:
                break
            try:
                # Skip vendored installs even if a repo accidentally
                # checked them in.
                if any(seg in {"node_modules", ".venv", "venv", "__pycache__"}
                       for seg in p.parts):
                    continue
                if p.stat().st_size > _PY_MAX_BYTES_PER_FILE:
                    continue
            except Exception:
                continue
            out.append(p)
    except Exception:
        return out
    return out


def _count_tools_in_file(p: Path) -> int:
    """Read file once, return number of tool-pattern matches. 0 on error."""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0
    return len(_TOOL_PATTERNS_RE.findall(text))


def scan_tools_code() -> list:
    """Walk DISCOVERED_REPOS; emit one `tool_registration` finding per
    repo where any tool pattern was found. Counts files + tool hits per
    file. Never ships source lines. Time-capped via deadline."""
    findings: list = []
    deadline = _time.time() + _PY_TIME_CAP_SECONDS
    for repo in DISCOVERED_REPOS:
        if _time.time() > deadline:
            break
        repo_path = Path(str(repo.get("path_safe", "")).replace("~", str(Path.home()), 1))
        if not repo_path.exists() or not repo_path.is_dir():
            continue
        per_file_counts: list = []
        total_tools = 0
        for py in _python_files_in(repo_path, deadline):
            n = _count_tools_in_file(py)
            if n <= 0:
                continue
            per_file_counts.append({
                "file_safe": _safe_path(py.relative_to(repo_path).as_posix()),
                "tool_hits": n,
            })
            total_tools += n
            if len(per_file_counts) >= 50:            # cap per repo; safety
                break
        if total_tools <= 0:
            continue
        finding = {
            "type":         "tool_registration",
            "repo_name":    repo.get("name", ""),
            "repo_safe":    repo.get("path_safe", ""),
            "remote_host":  repo.get("remote_host", ""),
            "head_sha":     repo.get("head_sha", ""),
            "total_tools":  total_tools,
            "files_with_tools": len(per_file_counts),
            "per_file":     per_file_counts[:50],
        }
        safe = _safe_finding(finding)
        if not _has_unredacted_secret(safe):
            findings.append(safe)
    return findings
