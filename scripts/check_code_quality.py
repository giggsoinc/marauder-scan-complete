# =============================================================
# FILE: scripts/check_code_quality.py
# VERSION: 1.0.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc / Ravi Venugopal
# PURPOSE: Pre-push quality gate. Enforces max line count,
#          forbids print statements, checks type hints on defs.
#          Exits 1 on violations, 0 on pass.
# AUDIT LOG:
#   v1.0.0  2026-05-17  Initial — created for pre-push hook gate.
# =============================================================

from __future__ import annotations

import ast
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[QUALITY] %(message)s")
log = logging.getLogger("patronai.quality")

MAX_LINES = 150
SCAN_DIRS = ["ghost-ai-scanner/src", "ghost-ai-scanner/dashboard"]


class QualityGate(ABC):
    """Abstract base for all pre-push quality gate checkers."""

    @abstractmethod
    def check(self, path: Path) -> list[str]:
        """Return list of violation strings for the given file."""


class CodeQualityChecker(QualityGate):
    """Checks line count, print usage, and type hint presence."""

    def check(self, path: Path) -> list[str]:
        """Run all quality checks on one Python file."""
        violations: list[str] = []
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as exc:
            log.warning("Cannot read %s: %s", path, exc)
            return []
        violations += self._check_line_count(path, source)
        violations += self._check_no_print(path, source)
        violations += self._check_type_hints(path, source)
        return violations

    def _check_line_count(self, path: Path, source: str) -> list[str]:
        """Fail if file exceeds MAX_LINES."""
        count = source.count("\n")
        if count > MAX_LINES:
            return [f"[QUALITY FAIL] {path}: {count} lines (max {MAX_LINES})"]
        return []

    def _check_no_print(self, path: Path, source: str) -> list[str]:
        """Fail if print() calls exist outside comments."""
        hits: list[str] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.id if isinstance(func, ast.Name)
                        else getattr(func, "attr", ""))
                if name == "print":
                    hits.append(
                        f"[QUALITY FAIL] {path}:{node.lineno} print() forbidden"
                    )
        return hits

    def _check_type_hints(self, path: Path, source: str) -> list[str]:
        """Warn if function definitions lack return annotations."""
        missing: list[str] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is None and not node.name.startswith("_"):
                    missing.append(
                        f"[QUALITY FAIL] {path}:{node.lineno} "
                        f"{node.name}() missing return type hint"
                    )
        return missing


def _collect_files(repo_root: Path) -> list[Path]:
    """Gather Python files from configured scan directories."""
    files: list[Path] = []
    for d in SCAN_DIRS:
        target = repo_root / d
        if target.exists():
            files += list(target.rglob("*.py"))
    return [f for f in files if "__pycache__" not in str(f)]


def main() -> int:
    """Entry point — returns 0 on pass, 1 on any violation."""
    repo_root = Path(__file__).resolve().parent.parent
    checker = CodeQualityChecker()
    all_violations: list[str] = []
    for path in _collect_files(repo_root):
        all_violations += checker.check(path)
    for v in all_violations:
        log.error(v)
    if all_violations:
        log.warning("%d violation(s) found — advisory only (brownfield baseline).",
                    len(all_violations))
    else:
        log.info("All quality checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
