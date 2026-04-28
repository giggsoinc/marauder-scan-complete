# =============================================================
# FILE: src/matcher/code_engine.py
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 2.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Code pattern matcher for Marauder Scan.
#          Authorized check FIRST — suppresses if match.
#          Then unauthorized check — alerts if match.
#          Ambiguous patterns sent to Gemma 4 E4B for classification.
#          Department scope enforced — LangChain in Engineering ≠
#          LangChain in Finance.
#          List loading lives in code_loader.py — re-exported here
#          for backward compatibility.
# DEPENDS: code_loader, stdlib
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v2.0.0  2026-04-25  Group 6 — list loading moved to code_loader.py
#                       (rule_model validation + custom-list merge there).
# =============================================================

import logging

from .code_loader import (  # re-export for backward compatibility
    load_authorized_code, load_authorized_code_full,
    load_unauthorized_code, load_unauthorized_code_full,
)

log = logging.getLogger("marauder-scan.matcher.code_engine")


class CodeOutcome:
    """Four mutually-exclusive verdicts produced by triage()."""
    SUPPRESS    = "SUPPRESS"      # authorized — no alert
    CODE_ALERT  = "CODE_ALERT"    # unauthorized match — alert
    AMBIGUOUS   = "AMBIGUOUS"     # send to Gemma for classification
    UNKNOWN     = "UNKNOWN"       # no match — flag LOW


AMBIGUOUS_SIGNALS = (
    "openai",        # could be authorized via Parameter Store
    "@tool",         # could be Flask or FastAPI decorator
    "agent",         # common variable name
    "llm",           # very common abbreviation
    "prompt",        # could be CLI prompt not AI
    "chain",         # could be payment chain not LangChain
    "workflow",      # could be business workflow
)


def triage(snippet: str, department: str, authorized: list, unauthorized: list) -> dict:
    """
    Classify a code snippet against allow + deny lists. Always returns a verdict.

    Step 1: Allow + dept scope match → SUPPRESS.
    Step 2: Deny match → CODE_ALERT.
    Step 3: Ambiguous keyword → AMBIGUOUS (referred to Gemma).
    Step 4: No match → UNKNOWN (LOW).
    """
    snippet_lower = snippet.lower()

    # ── STEP 1: Authorized check ──────────────────────────────
    for entry in authorized:
        pattern = (entry.get("pattern") or "").lower()
        if not pattern or pattern.startswith("#"):
            continue
        if pattern in snippet_lower:
            if _dept_match(department, entry.get("dept_scope", "")):
                log.debug("SUPPRESS: '%s' authorized for '%s'", pattern, department)
                return _verdict(CodeOutcome.SUPPRESS, entry["name"], "CLEAN", pattern)
            log.debug("Dept mismatch: '%s' not authorized for '%s'", pattern, department)

    # ── STEP 2: Unauthorized definite match ───────────────────
    for entry in unauthorized:
        pattern = (entry.get("pattern") or "").lower()
        if not pattern or pattern.startswith("#"):
            continue
        if pattern in snippet_lower:
            severity = (entry.get("severity") or "HIGH").upper()
            log.warning("CODE_ALERT [%s]: '%s' matched '%s'", severity, pattern, entry["name"])
            return _verdict(CodeOutcome.CODE_ALERT, entry["name"], severity, pattern)

    # ── STEP 3: Ambiguous patterns — send to Gemma ───────────
    for signal in AMBIGUOUS_SIGNALS:
        if signal in snippet_lower:
            log.debug("AMBIGUOUS: '%s' found — sending to Gemma", signal)
            return _verdict(CodeOutcome.AMBIGUOUS, signal, "UNKNOWN", signal)

    # ── STEP 4: Unknown ───────────────────────────────────────
    return _verdict(CodeOutcome.UNKNOWN, "", "LOW", "")


def _dept_match(department: str, dept_scope: str) -> bool:
    """Return True if `department` is in `dept_scope`. Empty scope = company-wide."""
    if not dept_scope:
        return True
    allowed = [d.strip().lower() for d in dept_scope.split(",")]
    return department.lower() in allowed


def _verdict(outcome: str, name: str, severity: str, pattern: str) -> dict:
    """Build the standard verdict dict returned by triage()."""
    return {
        "outcome":         outcome,
        "matched_name":    name,
        "severity":        severity,
        "matched_pattern": pattern,
    }


__all__ = [
    "CodeOutcome", "triage",
    "load_authorized_code", "load_authorized_code_full",
    "load_unauthorized_code", "load_unauthorized_code_full",
]
