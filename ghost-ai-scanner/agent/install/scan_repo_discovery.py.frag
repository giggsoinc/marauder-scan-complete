# =============================================================
# FRAGMENT: scan_repo_discovery.py.frag
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Auto-discover git repos under $HOME by walking for .git
#          directories. NO hardcoded paths — works on any laptop layout.
#          Honours noise-dir exclusions, depth-cap, and time-cap so the
#          walk never runs away on a huge filesystem. Provides
#          DISCOVERED_REPOS to scan_tools_code + scan_vector_dbs so they
#          stay inside repos and don't trawl the whole home dir.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A.
# =============================================================

import time as _time

# Names skipped wherever they appear in the path. Editable via
# config/repo_discovery.yaml on the server side; baked-in defaults here
# so the agent works standalone even if YAML is missing.
_REPO_EXCLUDE_NAMES = {
    "node_modules", ".venv", "venv", "vendor", "__pycache__",
    ".tox", ".gradle", ".m2", ".cargo", ".cache", ".docker",
    "Library", "Applications", ".Trash", "private",
    ".npm", ".pnpm", ".yarn", ".rustup", ".pyenv", ".rbenv",
    "Pictures", "Music", "Movies", "Public",
}
_REPO_MAX_DEPTH    = 6      # depth-cap from $HOME
_REPO_MAX_SECONDS  = 60.0   # hard time-cap; ship partial results on timeout


def _git_remote_host(repo_root: Path) -> str:
    """Best-effort: extract `github.com` / `gitlab.com` from .git/config.
    Strips any embedded user:token@ prefix to avoid shipping creds."""
    cfg = repo_root / ".git" / "config"
    if not cfg.exists():
        return ""
    try:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    m = re.search(r"url\s*=\s*[^@\s]*@?([A-Za-z0-9._\-]+(?:\.[A-Za-z]{2,})+)", text)
    return m.group(1).lower() if m else ""


def _git_head_sha(repo_root: Path) -> str:
    """Return short HEAD sha (first 7 chars) or '' if unreadable. No subprocess."""
    head = repo_root / ".git" / "HEAD"
    if not head.exists():
        return ""
    try:
        ref = head.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if ref.startswith("ref: "):
        ref_path = repo_root / ".git" / ref[5:]
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8").strip()[:7]
            except Exception:
                return ""
    return ref[:7] if re.fullmatch(r"[0-9a-f]{40}", ref) else ""


def _walk_for_repos(root: Path, deadline: float) -> list:
    """Depth-first walk under `root`; collect dirs that contain `.git/`.
    Skips noise dirs and obeys the deadline."""
    found: list = []
    stack: list = [(root, 0)]
    while stack and _time.time() < deadline:
        current, depth = stack.pop()
        if depth > _REPO_MAX_DEPTH:
            continue
        try:
            children = list(current.iterdir())
        except Exception:
            continue
        if any(c.name == ".git" and c.is_dir() for c in children):
            found.append(current)                     # this is a repo root
            continue                                  # don't recurse into a repo
        for child in children:
            if not child.is_dir() or child.is_symlink():
                continue
            if child.name in _REPO_EXCLUDE_NAMES or child.name.startswith("."):
                # Hidden dirs skipped except common dev hidden dirs
                if child.name not in (".github", ".gitlab"):
                    continue
            stack.append((child, depth + 1))
    return found


def discover_repos(root=None) -> list:
    """Return a list of discovered repo dicts under $HOME (or `root`).
    Each dict: {path_safe, name, head_sha, remote_host}.
    Time-capped at 60s; returns whatever was found on timeout."""
    home = Path(root) if root else Path.home()
    deadline = _time.time() + _REPO_MAX_SECONDS
    repos = _walk_for_repos(home, deadline)
    out: list = []
    for r in repos:
        out.append({
            "path_safe":   _safe_path(r),
            "name":        r.name,
            "head_sha":    _git_head_sha(r),
            "remote_host": _git_remote_host(r),
        })
    return out


# Compute once at scan time so downstream scanners reuse the result.
DISCOVERED_REPOS: list = []
try:
    DISCOVERED_REPOS = discover_repos()
except Exception:
    DISCOVERED_REPOS = []
