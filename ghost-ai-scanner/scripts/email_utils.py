# =============================================================
# FILE: scripts/email_utils.py
# VERSION: 2.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Shared SES email helpers for PatronAI.
#          - send_welcome_email: notifies a newly-onboarded user that
#            they have been added to the system.
#          - ensure_recipient_verified: triggers AWS SES email-identity
#            verification for a recipient. AWS sends them a one-click
#            verification link; until they click it, SES sandbox mode
#            refuses to send TO that address. Idempotent — calling for
#            an already-verified address is a no-op.
#
#          Why this matters: SES sandbox requires BOTH sender AND
#          recipient to be verified. Welcome emails worked because the
#          admins doing the onboarding were already verified. Agent
#          OTP emails to new fleet recipients failed silently because
#          those recipients were never verified. Now: every user added
#          to the system gets verified during the welcome flow, so
#          subsequent agent-deploy emails to them succeed even while
#          SES is still in sandbox.
#
#          Long-term: request SES production access (one-time AWS
#          support ticket); after approval, recipient verification is
#          no longer required and ensure_recipient_verified() becomes
#          a harmless no-op for unknown recipients too.
# DEPENDS: boto3, SES_SENDER_EMAIL env var, SES_REGION/AWS_REGION env var
#          IAM: ses:SendEmail, ses:VerifyEmailIdentity (already in
#          iam-policy.json under Sid HookAgentsSES).
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial. Extracted as shared util.
#   v2.0.0  2026-05-02  Add ensure_recipient_verified(); call it from
#                       send_welcome_email so registered users become
#                       verified SES identities. Fixes "Email failed —
#                       share OTP manually" on agent deploy when SES
#                       is in sandbox mode and recipient was never
#                       verified.
# =============================================================

import logging
import os
from typing import Optional

log = logging.getLogger("patronai.email_utils")


# ── Internal helpers ─────────────────────────────────────────────


def _ses_region() -> str:
    """SES region: SES_REGION env var, falling back to AWS_REGION."""
    return (os.environ.get("SES_REGION")
            or os.environ.get("AWS_REGION", "us-east-1"))


def _ses_sender(company: str = "") -> str:
    """Resolved sender identity. Logs a WARN if falling back."""
    sender = os.environ.get("SES_SENDER_EMAIL")
    if sender:
        return sender
    co = company or os.environ.get("COMPANY_NAME", "PatronAI")
    fallback = f"patronai@{co.lower()}.com"
    log.warning("SES_SENDER_EMAIL not set; using fallback %s — verify "
                "this address in SES or set SES_SENDER_EMAIL", fallback)
    return fallback


def _ses_err_code(exc: Exception) -> str:
    """Pull the boto3 ClientError code (MessageRejected,
    MailFromDomainNotVerified, etc.) out of an exception, falling back
    to the exception class name."""
    code = getattr(getattr(exc, "response", {}), "get",
                   lambda *_: {})("Error", {}).get("Code", "")
    return code or type(exc).__name__


# ── Public: ensure recipient is a verified SES identity ─────────


def ensure_recipient_verified(recipient_email: str,
                                region: Optional[str] = None) -> dict:
    """Trigger SES identity verification for the recipient.

    This is the function that lets us send transactional email (welcome,
    agent OTP, etc.) to fleet users while SES is still in sandbox mode.
    It calls `ses:VerifyEmailIdentity` which:

      - If the address is already verified → no email sent, no error.
      - If verification is pending → AWS may resend the verification
        email (depends on SES throttling).
      - If never seen before → AWS sends a one-click verification email
        to the recipient. Until they click it, SES rejects sends to them
        with `MessageRejected` ("Email address is not verified").

    Returns a dict so the caller can act on the outcome:
      {"action": "verified" | "already_verified" | "pending" | "error",
       "status": <SES VerificationStatus or "" if unknown>,
       "recipient": <email>,
       "region": <region>,
       "error": <message if action == "error">}

    Idempotent + safe to call on every welcome flow. Errors are
    swallowed (logged only) so a transient SES outage never blocks
    user registration.
    """
    import boto3

    region = region or _ses_region()
    addr = (recipient_email or "").strip()
    if not addr or "@" not in addr:
        return {"action": "error", "recipient": addr, "region": region,
                "status": "", "error": "invalid recipient email"}

    try:
        ses = boto3.client("ses", region_name=region)
        # Check current status FIRST so we don't trigger a re-send on
        # already-verified addresses (avoids inbox noise).
        attrs = ses.get_identity_verification_attributes(Identities=[addr])
        status = (attrs.get("VerificationAttributes", {})
                       .get(addr, {})
                       .get("VerificationStatus", ""))
        if status == "Success":
            log.debug("ensure_recipient_verified: %s already verified", addr)
            return {"action": "already_verified", "status": status,
                    "recipient": addr, "region": region}

        # Not verified (or Pending). Trigger verification — AWS sends
        # the recipient a click-to-verify email.
        ses.verify_email_identity(EmailAddress=addr)
        log.info("ensure_recipient_verified: triggered verification for %s "
                 "in region=%s (was status=%s)", addr, region, status or "unknown")
        return {"action": "pending" if status == "Pending" else "verified",
                "status": status or "Pending",
                "recipient": addr, "region": region}
    except Exception as exc:
        # Don't fail the calling flow — just log + report.
        err = _ses_err_code(exc)
        log.warning("ensure_recipient_verified failed for %s — region=%s "
                    "code=%s message=%s", addr, region, err, exc)
        return {"action": "error", "status": "", "recipient": addr,
                "region": region, "error": f"{err}: {exc}"}


# ── Public: send the welcome email (now also auto-verifies) ─────


def send_welcome_email(
    recipient_email: str,
    recipient_name: str,
    added_by: str,
    role: str,
    company: str = "",
) -> bool:
    """Send a welcome / onboarding notification via AWS SES.

    Side effect: also calls ensure_recipient_verified() so the new user
    gets an AWS SES verification email at the same time. Once they
    click the verification link, SES (even in sandbox mode) will accept
    sends TO them — which means subsequent agent OTP emails to this
    user via render_agent_package._send_email() will succeed instead of
    failing with `Email failed — share OTP manually`.

    Args:
        recipient_email:  New user's email address (To:).
        recipient_name:   Display name used in the greeting.
        added_by:         Admin email that triggered the add.
        role:             Assigned role (exec / manager / support).
        company:          Tenant name — falls back to COMPANY_NAME env var.

    Returns:
        True on send success, False on any SES / config error. Note: the
        verification side-effect is best-effort; its failure does not
        change the return value.
    """
    import boto3

    company  = company or os.environ.get("COMPANY_NAME", "PatronAI")
    region   = _ses_region()
    sender   = _ses_sender(company)
    dashboard_url = os.environ.get("PATRONAI_DASHBOARD_URL",
                                    "https://your-patronai-dashboard")

    # Best-effort: kick off SES recipient verification BEFORE the welcome
    # send. AWS will queue the verification email; the welcome email goes
    # out separately. Both arrive in the recipient's inbox.
    verify_result = ensure_recipient_verified(recipient_email, region=region)
    verify_action = verify_result.get("action", "unknown")

    # If verification just got triggered (recipient is brand-new to SES
    # and we're in sandbox), the welcome SEND below will FAIL until the
    # recipient clicks the verification link. We try anyway — production
    # accounts won't have this constraint, and the failure logging makes
    # it obvious to the operator what's happening.
    subject = f"Welcome to PatronAI — {company}"
    body = (
        f"Hi {recipient_name},\n\n"
        f"You have been added to the PatronAI security dashboard "
        f"for {company}.\n\n"
        f"  Role:      {role}\n"
        f"  Added by:  {added_by}\n\n"
        f"Log in here:\n"
        f"  {dashboard_url}\n\n"
        f"PatronAI monitors AI tool usage across your organisation "
        f"and surfaces security findings for your team.\n\n"
        f"You may also receive a separate email from "
        f"'no-reply-aws@amazon.com' asking you to verify your address "
        f"with AWS. Click the link in that email — it lets PatronAI "
        f"send you future notifications (agent installers, alerts, "
        f"reports) without manual intervention.\n\n"
        f"If you have questions, reply to this email or contact "
        f"your administrator ({added_by}).\n\n"
        f"— PatronAI · {company}\n"
    )

    try:
        ses = boto3.client("ses", region_name=region)
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient_email]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}},
            },
        )
        log.info("Welcome email sent to %s (role=%s, added_by=%s, "
                 "verify=%s)", recipient_email, role, added_by, verify_action)
        return True
    except Exception as exc:
        log.error("SES welcome email failed for %s — sender=%s region=%s "
                  "verify=%s code=%s message=%s",
                  recipient_email, sender, region, verify_action,
                  _ses_err_code(exc), exc)
        return False
