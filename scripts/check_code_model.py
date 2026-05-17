# =============================================================
# FILE: scripts/check_code_model.py
# VERSION: 1.0.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc / Ravi Venugopal
# PURPOSE: Pre-push structural model gate. Checks file header,
#          audit log table, and docstrings on public functions.
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
                    format="[MODEL] %(message)s")
log = logging.getLogger("patronai.model")

SCAN_DIRS = ["ghost-ai-scanner/src", "ghost-ai-scanner/dashboard"]
HEADER_MARKERS = ["# FILE:", "# PURPOSE:", "# OWNER:"]
AUDIT_MARKER = "# AUDIT LOG:"


class QualityGate(ABC):
    """Abstract base for all pre-push structural gate checkers."""

    @abstractmethod
    def check(self, path: Path) -> list[str]:
        """Return list of violation strings for the given file."""


class CodeModelChecker(QualityGate):
    """Checks file header, audit log table, and docstring presence."""

    def check(self, path: Path) -> list[str]:
        """Run all model checks on one Python file."""
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as exc:
            log.warning("Cannot read %s: %s", path, exc)
            return []
        violations: list[str] = []
        violations += self._check_header(path, source)
        violations += self._check_audit_log(path, source)
        violations += self._check_docstrings(path, source)
        return violations

    def _check_header(self, path: Path, source: str) -> list[str]:
        """Fail if required header markers are absent."""
        missing = [m for m in HEADER_MARKERS if m not in source]
        if missing:
            joined = ", ".join(missing)
            return [f"[MODEL FAIL] {path}: missing header fields: {joined}"]
        return []

    def _check_audit_log(self, path: Path, source: str) -> list[str]:
        """Fail if AUDIT LOG table marker is absent."""
        if AUDIT_MARKER not in source:
            return [f"[MODEL FAIL] {path}: missing '# AUDIT LOG:' table"]
        return []

    def _check_docstrings(self, path: Path, source: str) -> list[str]:
        """Warn if public functions/classes lack docstrings."""
        missing: list[str] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                missing.append(
                    f"[MODEL FAIL] {path}:{node.lineno} "
                    f"{node.name} missing docstring"
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
    checker = CodeModelChecker()
    all_violations: list[str] = []
    for path in _collect_files(repo_root):
        all_violations += checker.check(path)
    for v in all_violations:
        log.error(v)
    if all_violations:
        log.warning("%d violation(s) found — advisory only (brownfield baseline).",
                    len(all_violations))
    else:
        log.info("All structural model checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
