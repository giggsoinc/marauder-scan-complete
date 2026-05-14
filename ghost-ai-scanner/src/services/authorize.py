# =============================================================
# FILE: src/services/authorize.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Write per-user authorized-provider lists to S3 so the hook
#          agent can fetch them on next scan and stop emitting noise
#          for tools the operator has explicitly approved.
#          Storage layout:
#              s3://<bucket>/config/authorized/{email_safe}.json
#          Body:
#              {"version": 1, "updated_at": "...", "providers": [...]}
#          Companion scan_authorize_fetch.py.frag pulls this at scan
#          time. Findings whose provider is in the list never reach
#          the dashboard.
# DEPENDS: store.base_store (any blob store)
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("marauder-scan.services.authorize")

# Same character set as we use elsewhere for filesystem-safe email.
_EMAIL_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]")


def _safe_email(email: str) -> str:
    """Filesystem-safe email — replaces @ + special chars with _."""
    return _EMAIL_SAFE_RE.sub("_", (email or "").strip().lower())


def _key_for(email: str) -> str:
    """S3 key for one user's authorized list."""
    return f"config/authorized/{_safe_email(email)}.json"


def load_authorized(store, email: str) -> dict:
    """Read the current authorized list for a user.
    Returns {"version": 1, "updated_at": "...", "providers": [...]}
    or a fresh empty doc if none exists yet."""
    if not email:
        return {"version": 1, "providers": [], "updated_at": ""}
    try:
        raw = store.findings._get(_key_for(email))
        if not raw:
            return {"version": 1, "providers": [], "updated_at": ""}
        doc = json.loads(raw.decode())
        # Tolerate older shapes — coerce to canonical.
        return {
            "version":    int(doc.get("version", 1)),
            "providers":  sorted(set(doc.get("providers", []))),
            "updated_at": doc.get("updated_at", ""),
        }
    except Exception as exc:
        log.error("load_authorized failed for %s: %s", email, exc)
        return {"version": 1, "providers": [], "updated_at": ""}


def authorize(store, email: str, providers: list) -> int:
    """Add `providers` to the user's authorized list. Idempotent —
    duplicates collapse. Returns the new total count after merge."""
    if not email or not providers:
        return 0
    doc = load_authorized(store, email)
    merged = sorted(set(doc["providers"]) | set(str(p) for p in providers if p))
    new_doc = {
        "version":    1,
        "providers":  merged,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(new_doc, indent=2).encode()
    try:
        store.findings._put(_key_for(email), body, "application/json")
        log.info("authorize: %s now has %d entries (added %s)",
                 email, len(merged), providers)
    except Exception as exc:
        log.error("authorize put failed for %s: %s", email, exc)
        return len(doc["providers"])
    return len(merged)


def revoke(store, email: str, providers: list) -> int:
    """Remove `providers` from the user's authorized list.
    Returns the new total count after removal."""
    if not email or not providers:
        return 0
    doc = load_authorized(store, email)
    remaining = sorted(set(doc["providers"]) - set(str(p) for p in providers if p))
    new_doc = {
        "version":    1,
        "providers":  remaining,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(new_doc, indent=2).encode()
    try:
        store.findings._put(_key_for(email), body, "application/json")
    except Exception as exc:
        log.error("revoke put failed for %s: %s", email, exc)
    return len(remaining)
