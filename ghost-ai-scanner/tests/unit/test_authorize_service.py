# =============================================================
# FILE: tests/unit/test_authorize_service.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc
# PURPOSE: Lock the authorize service — once a user authorises a
#          tool, the agent must see it forever (unless revoked).
# =============================================================

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from services.authorize import (
    authorize, revoke, load_authorized, _safe_email, _key_for,
)


class _StubFindings:
    """Minimal stub for the FindingsStore — only _get and _put used."""
    def __init__(self):
        self._blob = {}
    def _get(self, key):
        return self._blob.get(key)
    def _put(self, key, body, ctype):
        self._blob[key] = body
        return True


class _StubStore:
    def __init__(self):
        self.findings = _StubFindings()


def test_safe_email_strips_at_and_special_chars():
    assert _safe_email("Ravi@Giggso.COM") == "ravi_giggso.com"
    assert _safe_email("a+b@c.io") == "a_b_c.io"


def test_key_per_user_isolated():
    a = _key_for("a@x.com")
    b = _key_for("b@x.com")
    assert a != b
    assert a.startswith("config/authorized/")


def test_authorize_creates_new_doc():
    s = _StubStore()
    n = authorize(s, "ravi@giggso.com", ["cursor", "flowise"])
    assert n == 2
    doc = load_authorized(s, "ravi@giggso.com")
    assert sorted(doc["providers"]) == ["cursor", "flowise"]
    assert doc["updated_at"]


def test_authorize_is_idempotent():
    s = _StubStore()
    authorize(s, "ravi@giggso.com", ["cursor"])
    authorize(s, "ravi@giggso.com", ["cursor"])
    authorize(s, "ravi@giggso.com", ["cursor"])
    assert len(load_authorized(s, "ravi@giggso.com")["providers"]) == 1


def test_authorize_merges_lists():
    s = _StubStore()
    authorize(s, "ravi@giggso.com", ["cursor"])
    authorize(s, "ravi@giggso.com", ["flowise", "ollama"])
    providers = load_authorized(s, "ravi@giggso.com")["providers"]
    assert set(providers) == {"cursor", "flowise", "ollama"}


def test_revoke_removes_entries():
    s = _StubStore()
    authorize(s, "ravi@giggso.com", ["cursor", "flowise"])
    revoke(s, "ravi@giggso.com", ["cursor"])
    providers = load_authorized(s, "ravi@giggso.com")["providers"]
    assert providers == ["flowise"]


def test_empty_inputs_are_noop():
    s = _StubStore()
    assert authorize(s, "", ["cursor"]) == 0
    assert authorize(s, "ravi@giggso.com", []) == 0


def test_per_user_isolation():
    """Authorising for user A must not touch user B's list."""
    s = _StubStore()
    authorize(s, "a@giggso.com", ["cursor"])
    authorize(s, "b@giggso.com", ["flowise"])
    a = load_authorized(s, "a@giggso.com")["providers"]
    b = load_authorized(s, "b@giggso.com")["providers"]
    assert "flowise" not in a
    assert "cursor" not in b


def test_load_authorized_handles_garbage_gracefully():
    s = _StubStore()
    s.findings._blob[_key_for("x@y.com")] = b"not-json-at-all"
    doc = load_authorized(s, "x@y.com")
    assert doc["providers"] == []  # graceful fallback


def test_load_authorized_canonicalises_legacy_shapes():
    s = _StubStore()
    s.findings._blob[_key_for("x@y.com")] = json.dumps(
        {"providers": ["b", "a", "b"]}
    ).encode()
    doc = load_authorized(s, "x@y.com")
    assert doc["providers"] == ["a", "b"]   # sorted + unique
