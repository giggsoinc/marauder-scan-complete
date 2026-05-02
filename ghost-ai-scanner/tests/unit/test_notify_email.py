# =============================================================
# FILE: tests/unit/test_notify_email.py
# PROJECT: PatronAI — Marauder Scan
# VERSION: 2.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Tests for the unified notify.email module — the single SES
#          call site for the codebase. Covers:
#            - ensure_verified() idempotency + error handling
#            - send() recipient normalisation + auto_verify side effect
#            - send_welcome / send_agent_otp / send_alert wrappers
#            - shim layers (manager_tab_actions.send_alert_email,
#              render_agent_package._send_email) still call through
# =============================================================

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))


# ── ensure_verified ────────────────────────────────────────────


def _mock_ses(verification_status: str = "") -> MagicMock:
    """Build a MagicMock SES client where the verify-attributes reply
    says either "Success" / "Pending" / "" (never seen) for x@example.com."""
    ses = MagicMock()
    if verification_status:
        ses.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {
                "x@example.com": {"VerificationStatus": verification_status}
            }
        }
    else:
        ses.get_identity_verification_attributes.return_value = {
            "VerificationAttributes": {}
        }
    ses.verify_email_identity.return_value = {}
    ses.send_email.return_value = {}
    return ses


def test_ensure_verified_already_verified_skips_call(monkeypatch):
    from notify.email import ensure_verified
    ses = _mock_ses("Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    r = ensure_verified("x@example.com", region="us-east-1")
    assert r["action"] == "already_verified"
    assert ses.verify_email_identity.call_count == 0


def test_ensure_verified_unknown_triggers_verification(monkeypatch):
    from notify.email import ensure_verified
    ses = _mock_ses("")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    r = ensure_verified("x@example.com", region="us-east-1")
    assert r["action"] == "verified"
    ses.verify_email_identity.assert_called_once_with(EmailAddress="x@example.com")


def test_ensure_verified_pending_resends(monkeypatch):
    from notify.email import ensure_verified
    ses = _mock_ses("Pending")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    r = ensure_verified("x@example.com", region="us-east-1")
    assert r["action"] == "pending"
    ses.verify_email_identity.assert_called_once()


def test_ensure_verified_invalid_short_circuits(monkeypatch):
    from notify.email import ensure_verified
    ses = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    for bad in ("", "  ", "no-at", None):
        r = ensure_verified(bad or "", region="us-east-1")
        assert r["action"] == "error"
    assert ses.method_calls == []


def test_ensure_verified_aws_error_does_not_raise(monkeypatch):
    from notify.email import ensure_verified
    ses = MagicMock()
    ses.get_identity_verification_attributes.side_effect = Exception("AccessDenied")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    r = ensure_verified("x@example.com", region="us-east-1")
    assert r["action"] == "error"


# ── send (single SES call site) ────────────────────────────────


def test_send_str_recipient(monkeypatch):
    from notify.email import send
    ses = _mock_ses("Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    ok = send("x@example.com", "Subj", "Body")
    assert ok is True
    args = ses.send_email.call_args.kwargs
    assert args["Destination"]["ToAddresses"] == ["x@example.com"]
    assert args["Source"] == "noreply@example.com"


def test_send_list_of_recipients(monkeypatch):
    from notify.email import send
    ses = _mock_ses("Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    ok = send(["a@x.com", "b@x.com"], "Subj", "Body")
    assert ok is True
    assert ses.send_email.call_args.kwargs["Destination"]["ToAddresses"] == \
        ["a@x.com", "b@x.com"]


def test_send_skips_verification_when_disabled(monkeypatch):
    from notify.email import send
    ses = _mock_ses("Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    send("x@example.com", "S", "B", auto_verify=False)
    # get_identity_verification_attributes should NOT have been called.
    assert ses.get_identity_verification_attributes.call_count == 0


def test_send_failure_returns_false(monkeypatch):
    from notify.email import send
    ses = _mock_ses("Success")
    ses.send_email.side_effect = Exception("MessageRejected")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    assert send("x@example.com", "S", "B") is False


def test_send_no_recipients_returns_false(monkeypatch):
    from notify.email import send
    ses = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.setenv("SES_SENDER_EMAIL", "noreply@example.com")
    assert send([], "S", "B") is False
    assert send([""], "S", "B") is False
    assert ses.send_email.call_count == 0


def test_send_falls_back_to_PATRONAI_FROM_EMAIL(monkeypatch):
    """Backwards compat: legacy alert path used PATRONAI_FROM_EMAIL.
    notify.email reads it as a fallback when SES_SENDER_EMAIL is missing."""
    from notify.email import send
    ses = _mock_ses("Success")
    monkeypatch.setattr("boto3.client", lambda *a, **kw: ses)
    monkeypatch.delenv("SES_SENDER_EMAIL", raising=False)
    monkeypatch.setenv("PATRONAI_FROM_EMAIL", "alerts@example.com")
    send("x@example.com", "S", "B")
    assert ses.send_email.call_args.kwargs["Source"] == "alerts@example.com"


# ── Convenience wrappers ───────────────────────────────────────


def test_send_welcome_calls_send_with_welcome_subject(monkeypatch):
    import notify.email as em
    captured = {}
    def _fake_send(recipient, subject, body, *, company="", auto_verify=True):
        captured.update(recipient=recipient, subject=subject, body=body,
                        auto_verify=auto_verify)
        return True
    monkeypatch.setattr(em, "send", _fake_send)
    em.send_welcome("alice@x.com", "Alice", "exec", "admin@x.com", "X")
    assert captured["recipient"] == "alice@x.com"
    assert "Welcome to PatronAI" in captured["subject"]
    assert "Alice" in captured["body"]
    assert "exec" in captured["body"]
    assert "admin@x.com" in captured["body"]


def test_send_agent_otp_includes_otp_and_url(monkeypatch):
    import notify.email as em
    captured = {}
    def _fake_send(recipient, subject, body, *, company="", auto_verify=True):
        captured.update(body=body, subject=subject)
        return True
    monkeypatch.setattr(em, "send", _fake_send)
    em.send_agent_otp("alice@x.com", "Alice", "621342",
                       "https://s3/installer.sh", "X")
    assert "PatronAI Agent" in captured["subject"]
    assert "621342" in captured["body"]
    assert "https://s3/installer.sh" in captured["body"]


def test_send_alert_bullets_each_event(monkeypatch):
    import notify.email as em
    captured = {}
    def _fake_send(recipient, subject, body, *, company="", auto_verify=True):
        captured.update(body=body, recipient=recipient)
        return True
    monkeypatch.setattr(em, "send", _fake_send)
    events = [
        {"severity": "CRITICAL", "provider": "openai", "owner": "alice@x.com",
         "timestamp": "2026-05-02T12:00:00+00:00"},
        {"severity": "HIGH", "provider": "claude", "owner": "bob@x.com",
         "timestamp": "2026-05-02T13:00:00+00:00"},
    ]
    em.send_alert("a@x.com,b@x.com", events)
    assert "2 event(s)" in captured["body"]
    assert "openai" in captured["body"] and "claude" in captured["body"]
    # Recipients comma-string was split.
    assert captured["recipient"] == ["a@x.com", "b@x.com"]


def test_send_alert_empty_events_returns_false():
    from notify.email import send_alert
    assert send_alert(["a@x.com"], []) is False


# ── Shims still delegate ───────────────────────────────────────


def test_manager_tab_actions_send_alert_email_delegates(monkeypatch):
    """The dashboard shim must call notify.email.send_alert and return
    its result without doing its own SES work."""
    sys.path.insert(0, str(REPO / "dashboard"))
    import notify.email as em
    seen = {}
    def _fake_send_alert(recipients, events):
        seen.update(recipients=recipients, events=events)
        return True
    monkeypatch.setattr(em, "send_alert", _fake_send_alert)
    from ui.manager_tab_actions import send_alert_email
    ok = send_alert_email([{"x": 1}], "a@x.com,b@x.com")
    assert ok is True
    assert seen["recipients"] == "a@x.com,b@x.com"
    assert seen["events"] == [{"x": 1}]


def test_render_agent_package_send_email_delegates(monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import notify.email as em
    seen = {}
    def _fake_send_otp(recipient, name, otp, installer_url, company=""):
        seen.update(recipient=recipient, otp=otp, url=installer_url)
        return True
    monkeypatch.setattr(em, "send_agent_otp", _fake_send_otp)
    from render_agent_package import _send_email
    ok = _send_email("Alice", "alice@x.com", "621342",
                     "https://s3/installer.sh", "X")
    assert ok is True
    assert seen == {"recipient": "alice@x.com",
                    "otp": "621342",
                    "url": "https://s3/installer.sh"}
