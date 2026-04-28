# =============================================================
# FILE: src/matcher/engine.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Core matching engine. Compares a normalized flat event
#          against authorized and unauthorized provider lists.
#          Returns a verdict for every event — four outcomes.
#          No event ever passes without a decision.
#          Token and personal key enrichment done in alerter.py.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: matcher.outcomes, fnmatch
# =============================================================

import logging
from fnmatch import fnmatch
from typing import Optional
from .outcomes import Outcome, make_verdict

log = logging.getLogger("marauder-scan.matcher.engine")


def match(
    event: dict,
    authorized: list,
    unauthorized: list,
) -> dict:
    """
    Compare a normalized flat event against provider lists.
    Returns a verdict dict with outcome, provider, category, severity.

    Step 1: Check authorized list — match means SUPPRESS.
    Step 2: Check unauthorized domain column — match means DOMAIN_ALERT.
    Step 3: Check unauthorized port column — match means PORT_ALERT.
    Step 4: No match anywhere — UNKNOWN. Never silently pass.
    """
    dst_domain = (event.get("dst_domain") or "").lower().rstrip(".")
    dst_port   = int(event.get("dst_port") or 0)

    # ── STEP 1: Authorized check ──────────────────────────────
    # Check first. Authorized domain suppresses everything else.
    if dst_domain:
        for entry in authorized:
            pattern = entry.get("domain_pattern", "").lower()
            if pattern and _domain_match(dst_domain, pattern):
                log.debug(f"SUPPRESS: {dst_domain} matched authorized {pattern}")
                return make_verdict(
                    outcome=Outcome.SUPPRESS,
                    provider=entry.get("name", "Authorized"),
                    notes=entry.get("notes", ""),
                )

    # ── STEP 2: Unauthorized domain match ────────────────────
    if dst_domain:
        verdict = _check_domain(dst_domain, unauthorized)
        if verdict:
            log.warning(
                f"DOMAIN_ALERT: {dst_domain} → {verdict['provider']} "
                f"[{verdict['severity']}]"
            )
            return verdict

    # ── STEP 3: Unauthorized port match ──────────────────────
    # Port-only entries have empty domain. Catches local AI servers.
    if dst_port:
        verdict = _check_port(dst_port, unauthorized)
        if verdict:
            log.warning(
                f"PORT_ALERT: port {dst_port} → {verdict['provider']} "
                f"[{verdict['severity']}]"
            )
            return verdict

    # ── STEP 4: Unknown — never silently pass ─────────────────
    log.debug(f"UNKNOWN: {dst_domain or dst_port} — flagged LOW for review")
    return make_verdict(
        outcome=Outcome.UNKNOWN,
        notes="No match in authorized or unauthorized list. Flagged for Giggso review.",
    )


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _domain_match(dst: str, pattern: str) -> bool:
    """
    Glob pattern match on domain.
    *.openai.com matches api.openai.com and chat.openai.com.
    Exact match also supported.
    """
    if not pattern or not dst:
        return False
    return fnmatch(dst, pattern)


def _check_domain(dst_domain: str, unauthorized: list) -> Optional[dict]:
    """
    Check destination domain against all unauthorized entries
    that have a domain pattern defined.
    Returns verdict dict on first match, None if no match.
    """
    for entry in unauthorized:
        pattern = entry.get("domain", "")
        if not pattern:
            continue
        if _domain_match(dst_domain, pattern):
            return make_verdict(
                outcome=Outcome.DOMAIN_ALERT,
                provider=entry["name"],
                category=entry["category"],
                severity=entry["severity"],
                matched_domain=dst_domain,
                notes=entry.get("notes", ""),
            )
    return None


def _check_port(dst_port: int, unauthorized: list) -> Optional[dict]:
    """
    Check destination port against unauthorized entries
    that have no domain (port-only entries).
    Catches local AI servers: Ollama 11434, LM Studio 1234.
    Always returns MEDIUM severity — no external transfer confirmed.
    """
    for entry in unauthorized:
        if entry.get("domain"):
            continue  # skip domain entries
        if entry.get("port") == dst_port:
            return make_verdict(
                outcome=Outcome.PORT_ALERT,
                provider=entry["name"],
                category=entry["category"],
                severity="MEDIUM",  # always MEDIUM for port-only
                matched_port=dst_port,
                notes=entry.get("notes", ""),
            )
    return None
