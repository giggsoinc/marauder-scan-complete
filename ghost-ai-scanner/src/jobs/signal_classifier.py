# =============================================================
# FILE: src/jobs/signal_classifier.py
# VERSION: 1.0.0
# UPDATED: 2026-05-17
# OWNER: Giggso Inc / Ravi Venugopal
# PURPOSE: Classify compacted findings as GHOST / NOISE / NO_ISSUE.
#          Phase 1: rule-based (occurrences + persistence).
#          Phase 2: LLM batch for UNKNOWN-outcome rows only.
#          Called by findings_compact.compact_day() after grouping.
# AUDIT LOG:
#   v1.0.0  2026-05-17  Initial. Phase 1 rules + Phase 2 LLM batch.
# =============================================================

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime

log = logging.getLogger("patronai.jobs.signal_classifier")

_MODEL   = os.environ.get("OPENAI_SIGNAL_MODEL", "gpt-4.1-mini")
_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_SCAN_S  = int(os.environ.get("SCAN_INTERVAL_SECS", "300"))
_GHOST_OCCS    = int(os.environ.get("GHOST_MIN_OCCURRENCES", "3"))
_GHOST_PERSIST = float(os.environ.get("GHOST_MIN_PERSIST_DAYS", "0.5"))


def _parse_ts(v: str | None) -> datetime | None:
    """Lenient ISO parse — returns None on bad input."""
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _persist_days(first: str | None, last: str | None) -> float:
    """Float days between first and last seen; 0.0 on parse error."""
    t0, t1 = _parse_ts(first), _parse_ts(last)
    if t0 and t1 and t1 > t0:
        return (t1 - t0).total_seconds() / 86400.0
    return 0.0


def _freq_pct(occs: int, first: str | None, last: str | None) -> float:
    """Ratio of actual occurrences to expected scans over the observed window."""
    p = _persist_days(first, last)
    if p <= 0 or _SCAN_S <= 0:
        return 1.0 if occs >= 1 else 0.0
    return min(1.0, occs / max(1, (p * 86400) / _SCAN_S))


def classify_rule(
    outcome: str, occurrences: int, first_seen: str | None, last_seen: str | None,
) -> str:
    """Phase 1 rule-based signal classification. Returns GHOST | NOISE | NO_ISSUE."""
    if outcome == "SUPPRESS":
        return "NO_ISSUE"
    p = _persist_days(first_seen, last_seen)
    if outcome in ("DOMAIN_ALERT", "PORT_ALERT"):
        return "GHOST" if (occurrences >= _GHOST_OCCS or p >= _GHOST_PERSIST) else "NOISE"
    if occurrences >= 5 and p >= 1.0:  # UNKNOWN — elevated bar
        return "GHOST"
    return "NOISE"


def _openai_call(prompt: str) -> str:
    """POST to OpenAI chat/completions. Returns content string or '' on error."""
    if not _API_KEY:
        return ""
    payload = json.dumps({
        "model": _MODEL, "temperature": 0, "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.warning("signal_classifier LLM call failed: %s", exc)
        return ""


def _llm_classify_unknown(rows: list[dict]) -> dict[str, tuple[str, str]]:
    """Batch LLM call for UNKNOWN rows. Returns {sig: (signal_class, reason)}."""
    if not rows or not _API_KEY:
        return {}
    items = [{
        "sig":       r.get("finding_signature", ""),
        "domain":    r.get("dst_domain", ""),
        "process":   r.get("process_name") or r.get("mcp_host", ""),
        "port":      r.get("dst_port", ""),
        "occs":      r.get("occurrences", 1),
        "persist_d": round(_persist_days(r.get("first_seen"), r.get("last_seen")), 2),
    } for r in rows]
    prompt = (
        "You are an AI governance analyst. Classify each item as GHOST or NOISE.\n"
        "GHOST = repeated AI API access, AI dev ports (11434,8080,5001), LLM providers.\n"
        "NOISE = package managers, OS telemetry, update checks, CI/CD, one-off DNS.\n"
        'Return ONLY valid JSON: {"<sig>":{"signal_class":"GHOST"|"NOISE","reason":"<8 words>"}}\n\n'
        f"Items:\n{json.dumps(items)}"
    )
    raw = _openai_call(prompt)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
        return {sig: (v.get("signal_class", "NOISE"), v.get("reason", ""))
                for sig, v in parsed.items() if isinstance(v, dict)}
    except Exception as exc:
        log.warning("signal_classifier LLM parse failed: %s — %.200r", exc, raw)
        return {}


def enrich_signal(rows: list[dict]) -> list[dict]:
    """Add signal_class/reason/persistence_days/scan_frequency_pct to each row.
    Phase 1 runs for all rows; Phase 2 LLM runs for UNKNOWN rows only."""
    for r in rows:
        outcome, occs = r.get("outcome", "UNKNOWN"), int(r.get("occurrences", 1))
        r["persistence_days"]   = round(_persist_days(r.get("first_seen"), r.get("last_seen")), 3)
        r["scan_frequency_pct"] = round(_freq_pct(occs, r.get("first_seen"), r.get("last_seen")), 3)
        r["signal_class"]       = classify_rule(outcome, occs, r.get("first_seen"), r.get("last_seen"))
        r["signal_reason"]      = "rule"
    unknown_rows = [r for r in rows if r.get("outcome") == "UNKNOWN" and _API_KEY]
    if unknown_rows:
        llm = _llm_classify_unknown(unknown_rows)
        for r in unknown_rows:
            sig = r.get("finding_signature", "")
            if sig in llm:
                r["signal_class"], r["signal_reason"] = llm[sig]
    return rows
