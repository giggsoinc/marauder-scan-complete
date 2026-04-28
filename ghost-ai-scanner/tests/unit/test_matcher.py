# =============================================================
# FILE: tests/unit/test_matcher.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Unit tests for network traffic matcher.
#          Tests all 4 outcomes and authorized-first logic.
#          No AWS calls.
# =============================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from matcher.engine   import match
from matcher.outcomes import Outcome

AUTHORIZED = [
    {"name": "Trinity", "domain_pattern": "trinity.internal.com", "notes": ""},
    {"name": "OpenAI Approved", "domain_pattern": "*.openai.com",  "notes": ""},
]

UNAUTHORIZED = [
    {"name": "OpenAI",      "category": "LLM API",          "domain": "*.openai.com",      "port": 0,     "severity": "HIGH"},
    {"name": "HuggingFace", "category": "Model Hub",         "domain": "*.huggingface.co",  "port": 0,     "severity": "HIGH"},
    {"name": "Ollama",      "category": "Local Inference",   "domain": "",                  "port": 11434, "severity": "MEDIUM"},
    {"name": "LM Studio",   "category": "Local Inference",   "domain": "",                  "port": 1234,  "severity": "MEDIUM"},
]


def _event(domain="", port=0):
    return {"dst_domain": domain, "dst_port": port}


# ── Authorized ────────────────────────────────────────────────

def test_authorized_exact_suppressed():
    v = match(_event("trinity.internal.com"), AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == Outcome.SUPPRESS


def test_authorized_wildcard_suppressed():
    """*.openai.com in authorized — chat.openai.com must suppress."""
    v = match(_event("chat.openai.com"), AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == Outcome.SUPPRESS


def test_authorized_checked_before_unauthorized():
    """Critical: authorized must fire BEFORE unauthorized."""
    # api.openai.com is in both lists — authorized wins
    v = match(_event("api.openai.com"), AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == Outcome.SUPPRESS


# ── Domain alerts ─────────────────────────────────────────────

def test_unauthorized_domain_alert():
    v = match(_event("api.huggingface.co"), [], UNAUTHORIZED)
    assert v["outcome"]  == Outcome.DOMAIN_ALERT
    assert v["provider"] == "HuggingFace"
    assert v["severity"] == "HIGH"


def test_wildcard_domain_match():
    v = match(_event("models.huggingface.co"), [], UNAUTHORIZED)
    assert v["outcome"] == Outcome.DOMAIN_ALERT


# ── Port alerts ───────────────────────────────────────────────

def test_ollama_port_alert():
    v = match(_event(port=11434), [], UNAUTHORIZED)
    assert v["outcome"]       == Outcome.PORT_ALERT
    assert v["severity"]      == "MEDIUM"
    assert v["matched_port"]  == 11434


def test_lm_studio_port_alert():
    v = match(_event(port=1234), [], UNAUTHORIZED)
    assert v["outcome"] == Outcome.PORT_ALERT


def test_port_alert_always_medium():
    """Port-only matches are always MEDIUM — no external transfer confirmed."""
    v = match(_event(port=11434), [], UNAUTHORIZED)
    assert v["severity"] == "MEDIUM"


# ── Unknown ───────────────────────────────────────────────────

def test_unknown_never_silently_passes():
    v = match(_event("some-random-saas.io"), [], UNAUTHORIZED)
    assert v["outcome"]  == Outcome.UNKNOWN
    assert v["severity"] == "LOW"


def test_empty_event_unknown():
    v = match(_event(), [], UNAUTHORIZED)
    assert v["outcome"] == Outcome.UNKNOWN


# ── Edge cases ────────────────────────────────────────────────

def test_empty_authorized_and_unauthorized():
    v = match(_event("api.openai.com"), [], [])
    assert v["outcome"] == Outcome.UNKNOWN


def test_domain_with_trailing_dot():
    """DNS sometimes appends a dot — normalizer strips it."""
    v = match(_event("api.huggingface.co."), [], UNAUTHORIZED)
    assert v["outcome"] == Outcome.DOMAIN_ALERT
