# =============================================================
# FILE: scripts/vuln_scan.py
# VERSION: 1.0.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc / Ravi Venugopal
# PURPOSE: Pre-push vulnerability gate. Scans for hardcoded
#          secrets, bare excepts, and dangerous patterns.
#          Exits 1 on CRITICAL/HIGH findings, 0 on pass.
# AUDIT LOG:
#   v1.0.0  2026-05-17  Initial — created for pre-push hook gate.
# =============================================================

from __future__ import annotations

import ast
import logging
import re
import sys
from abc import ABC, abstractmethod
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[VULN] %(message)s")
log = logging.getLogger("patronai.vuln")

SCAN_DIRS = ["ghost-ai-scanner/src", "ghost-ai-scanner/dashboard", "scripts"]

SECRET_PATTERNS: list[tuple[str, str, str]] = [
    (r"AKIA[0-9A-Z]{16}", "CRITICAL", "Hardcoded AWS access key"),
    (r"(?i)(password|passwd|secret|api_key)\s*=\s*['\"][^'\"]{4,}['\"]",
     "HIGH", "Hardcoded credential assignment"),
    (r"(?i)-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----",
     "CRITICAL", "Hardcoded private key"),
    (r"(?i)(token)\s*=\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]",
     "HIGH", "Hardcoded token"),
]

SKIP_FILES = {"check_code_quality.py", "check_code_model.py", "vuln_scan.py"}


class QualityGate(ABC):
    """Abstract base for all pre-push vulnerability gate checkers."""

    @abstractmethod
    def check(self, path: Path) -> list[tuple[str, str]]:
        """Return list of (severity, message) tuples for the given file."""


class VulnScanner(QualityGate):
    """Scans for hardcoded secrets and dangerous code patterns."""

    def check(self, path: Path) -> list[tuple[str, str]]:
        """Run secret and pattern scans on one Python file."""
        if path.name in SKIP_FILES:
            return []
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as exc:
            log.warning("Cannot read %s: %s", path, exc)
            return []
        results: list[tuple[str, str]] = []
        results += self._scan_secrets(path, source)
        results += self._scan_bare_except(path, source)
        return results

    def _scan_secrets(self, path: Path, source: str) -> list[tuple[str, str]]:
        """Regex scan for hardcoded secret patterns."""
        hits: list[tuple[str, str]] = []
        for line_no, line in enumerate(source.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for pattern, severity, desc in SECRET_PATTERNS:
                if re.search(pattern, line):
                    hits.append((severity,
                                 f"[VULN {severity}] {path}:{line_no} {desc}"))
        return hits

    def _scan_bare_except(self, path: Path, source: str) -> list[tuple[str, str]]:
        """AST scan for bare except: clauses."""
        hits: list[tuple[str, str]] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                hits.append(("HIGH",
                             f"[VULN HIGH] {path}:{node.lineno} "
                             f"bare except: catches all — use Exception"))
        return hits


def _collect_files(repo_root: Path) -> list[Path]:
    """Gather Python files from configured scan directories."""
    files: list[Path] = []
    for d in SCAN_DIRS:
        target = repo_root / d
        if target.exists():
            files += list(target.rglob("*.py"))
    return [f for f in files if "__pycache__" not in str(f)]


def main() -> int:
    """Entry point — returns 0 on pass, 1 on CRITICAL/HIGH findings."""
    repo_root = Path(__file__).resolve().parent.parent
    scanner = VulnScanner()
    blocking: list[str] = []
    for path in _collect_files(repo_root):
        for severity, msg in scanner.check(path):
            log.error(msg)
            if severity in ("CRITICAL", "HIGH"):
                blocking.append(msg)
    if blocking:
        log.error("%d blocking finding(s).", len(blocking))
        return 1
    log.info("Vulnerability scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
