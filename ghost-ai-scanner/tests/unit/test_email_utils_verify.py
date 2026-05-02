# =============================================================
# FILE: tests/unit/test_email_utils_verify.py
# PROJECT: PatronAI — Marauder Scan
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Tests for ensure_recipient_verified() — the SES sandbox
#          unblocker that lets PatronAI welcome + agent-OTP emails
#          reach unverified recipients without manual ses verify-
#          email-identity calls per address.
# =============================================================

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


# ── ensure_recipient_verified — happy + edge paths ───────────────


def _mock_ses(verification_status: str = ""):
    """Build a MagicMock that looks like a boto3 SES client.
    `verification_status` controls what get_identity_verification_attributes
    reports for the queried address: "" / "Pending" / "Success"."""
    ses = MagicMock()
    if verification_status:
        ses.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "x@example.com": {"VerificationStatus": verification_status}
            }
        }
    else:
        # Address never seen by SES → empty attrs map.
        ses.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {}
        }
    ses.verify_email_identity.return_value = {}
    return ses


def test_already_verified_skips_verify_call(monkeypatch):
    """If recipient is already verified, we MUST NOT trigger another
    verification email (would spam the inbox)."""
    from email_utils import ensure_recipient_verified

    ses = _mock_ses(verification_status="Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)

    r = ensure_recipient_verified("x@example.com", region="us-east-1")
    assert r["action"] == "already_verified"
    assert r["status"] == "Success"
    assert ses.verify_email_identity.call_count == 0


def test_unknown_recipient_triggers_verification(monkeypatch):
    """Brand-new address → SES verify-email-identity is called once."""
    from email_utils import ensure_recipient_verified

    ses = _mock_ses(verification_status="")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)

    r = ensure_recipient_verified("x@example.com", region="us-east-1")
    assert r["action"] == "verified"
    ses.verify_email_identity.assert_called_once_with(EmailAddress="x@example.com")


def test_pending_recipient_resends_verification(monkeypatch):
    """If status is Pending (verification email sent but not clicked),
    calling again is allowed — gives recipient a fresh link."""
    from email_utils import ensure_recipient_verified

    ses = _mock_ses(verification_status="Pending")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)

    r = ensure_recipient_verified("x@example.com", region="us-east-1")
    assert r["action"] == "pending"
    assert r["status"] == "Pending"
    ses.verify_email_identity.assert_called_once()


def test_invalid_email_short_circuits_no_aws_call(monkeypatch):
    """Garbage input doesn't reach AWS — fast fail with a clear error."""
    from email_utils import ensure_recipient_verified

    ses = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)

    for bad in ("", "   ", "not-an-email", None):
        r = ensure_recipient_verified(bad or "", region="us-east-1")
        assert r["action"] == "error"
        assert "invalid recipient email" in r["error"]
    assert ses.method_calls == []


def test_aws_error_does_not_raise(monkeypatch):
    """SES outage / IAM denial must NOT crash the welcome flow."""
    from email_utils import ensure_recipient_verified

    ses = MagicMock()
    ses.get_identity_verification_attributes.side_effect = Exception("AccessDenied")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)

    r = ensure_recipient_verified("x@example.com", region="us-east-1")
    assert r["action"] == "error"
    assert "AccessDenied" in r["error"] or "Exception" in r["error"]


# ── send_welcome_email — verify is invoked + return value preserved ─


def test_welcome_email_calls_ensure_verify(monkeypatch):
    """send_welcome_email MUST call ensure_recipient_verified, and the
    welcome's return value reflects only the SES send result, not the
    verification side-effect."""
    import email_utils

    sent = MagicMock()
    sent.send_email.return_value = {}
    monkeypatch.setattr("boto3.client", lambda *a, **kw: sent)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    monkeypatch.setenv("SES_REGION", "us-east-1")

    seen = {}
    def _fake_verify(addr, region=None):
        seen["addr"] = addr
        seen["region"] = region
        return {"action": "verified", "status": "Pending",
                "recipient": addr, "region": region}
    monkeypatch.setattr(email_utils, "ensure_recipient_verified", _fake_verify)

    sent.get_identity_verification_attributes.return_value = {
        "VerificationAttributes": {}
    }

    ok = email_utils.send_welcome_email(
        recipient_email="alice@x.com", recipient_name="Alice",
        added_by="admin@x.com", role="exec", company="X")
    assert ok is True
    assert seen["addr"] == "alice@x.com"
    assert seen["region"] == "us-east-1"
    sent.send_email.assert_called_once()


def test_welcome_email_send_failure_returns_false_even_if_verify_ok(monkeypatch):
    """Welcome's True/False is decoupled from verification outcome."""
    import email_utils

    sent = MagicMock()
    sent.send_email.side_effect = Exception("MessageRejected")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: sent)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    monkeypatch.setattr(email_utils, "ensure_recipient_verified",
                        lambda addr, region=None: {"action": "already_verified",
                                                     "status": "Success",
                                                     "recipient": addr,
                                                     "region": region})

    ok = email_utils.send_welcome_email(
        recipient_email="alice@x.com", recipient_name="Alice",
        added_by="admin@x.com", role="exec", company="X")
    assert ok is False
