# =============================================================
# FILE: scripts/email_utils.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Shared SES email helpers for PatronAI.
#          send_welcome_email — notifies a newly-onboarded user that
#          they have been added to the system, their role, and who added
#          them. Reuses the same boto3 SES client / env-var pattern as
#          render_agent_package._send_email() so no new AWS config is
#          needed.
# DEPENDS: boto3, SES_SENDER_EMAIL env var, AWS_REGION env var
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial. Extracted as shared util so users.py
#                       and any future onboarding path can import it
#                       without depending on render_agent_package.py.
# =============================================================

import logging
import os

log = logging.getLogger("patronai.email_utils")


def send_welcome_email(
    recipient_email: str,
    recipient_name: str,
    added_by: str,
    role: str,
    company: str = "",
) -> bool:
    """Send a welcome / onboarding notification via AWS SES.

    Args:
        recipient_email:  New user's email address (To:).
        recipient_name:   Display name used in the greeting.
        added_by:         Admin email that triggered the add.
        role:             Assigned role (exec / manager / support).
        company:          Tenant name — falls back to COMPANY_NAME env var.

    Returns:
        True on success, False on any SES / config error.
    """
    import boto3

    company  = company or os.environ.get("COMPANY_NAME", "PatronAI")
    region   = os.environ.get("AWS_REGION", "us-east-1")
    sender   = os.environ.get("SES_SENDER_EMAIL",
                               f"patronai@{company.lower()}.com")
    dashboard_url = os.environ.get("PATRONAI_DASHBOARD_URL",
                                    "https://your-patronai-dashboard")

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
        log.info("Welcome email sent to %s (role=%s, added_by=%s)",
                 recipient_email, role, added_by)
        return True
    except Exception as exc:
        log.error("SES welcome email failed for %s: %s", recipient_email, exc)
        return False
