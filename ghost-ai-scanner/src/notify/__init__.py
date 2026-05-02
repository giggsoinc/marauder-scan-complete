# =============================================================
# FILE: src/notify/__init__.py
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Notification package — single home for all outbound
#          messaging (email today, future SMS / Slack / webhook
#          variants slot in beside email.py without changing
#          callers' import path beyond `from notify import …`).
# =============================================================

from .email import (  # noqa: F401 — public API re-export
    send,
    send_welcome,
    send_agent_otp,
    send_alert,
    ensure_verified,
)

__all__ = [
    "send",
    "send_welcome",
    "send_agent_otp",
    "send_alert",
    "ensure_verified",
]
