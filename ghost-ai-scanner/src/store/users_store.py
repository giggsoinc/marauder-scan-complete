# =============================================================
# FILE: src/store/users_store.py
# PROJECT: PatronAI — Phase 1B
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: S3-backed CRUD for the user / role / admin map. Replaces the
#          ALLOWED_EMAILS + ADMIN_EMAILS env-var pair with a real
#          per-tenant `users.json` so admins can add / edit / remove
#          users from the dashboard without redeploying.
#          Schema (per email):
#            {
#              "role":     "exec" | "manager" | "support",
#              "is_admin": bool,
#              "added_at": ISO timestamp,
#              "added_by": admin email (or "migration" on first run)
#            }
#          On first run with no users.json present, migrates from
#          ALLOWED_EMAILS / ADMIN_EMAILS env vars (one-shot bootstrap).
# DEPENDS: store.base_store
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1B.
# =============================================================

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .base_store import BaseStore

log = logging.getLogger("marauder-scan.users_store")

USERS_KEY    = "users/users.json"
VALID_ROLES  = ("exec", "manager", "support")
DEFAULT_ROLE = "support"      # least-access default for safety

_ALLOWED_ENV = "ALLOWED_EMAILS"
_ADMINS_ENV  = "ADMIN_EMAILS"


class UsersStore(BaseStore):
    """Reads + writes the per-tenant users.json on S3."""

    def read_all(self) -> dict:
        """Return the full users dict.
        First call when users.json is absent triggers env-var migration."""
        raw = self._get(USERS_KEY)
        if not raw:
            return self._migrate_from_env()
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            log.error(f"users.json corrupt — returning empty map; "
                      f"will not auto-migrate (corruption is human-fix territory)")
            return {}

    def get(self, email: str) -> Optional[dict]:
        """Return one user's record; None if not present."""
        return self.read_all().get((email or "").lower())

    def upsert(self, email: str, role: str, is_admin: bool,
               added_by: str = "") -> bool:
        """Add or update a user. Validates role; refuses unknown roles."""
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            return False
        if role not in VALID_ROLES:
            log.warning(f"upsert refused — invalid role: {role}")
            return False
        users = self.read_all()
        existing = users.get(email, {})
        users[email] = {
            "role":     role,
            "is_admin": bool(is_admin),
            "added_at": existing.get("added_at",
                                     datetime.now(timezone.utc).isoformat()),
            "added_by": existing.get("added_by", added_by or "admin"),
        }
        return self._put(USERS_KEY,
                         json.dumps(users, indent=2).encode(),
                         "application/json")

    def remove(self, email: str) -> bool:
        """Delete a user. No-op if not present. Returns True on success."""
        email = (email or "").strip().lower()
        users = self.read_all()
        if email not in users:
            return True
        users.pop(email, None)
        return self._put(USERS_KEY,
                         json.dumps(users, indent=2).encode(),
                         "application/json")

    def is_authorised(self, email: str) -> bool:
        """Quick yes/no — used by the auth gate."""
        return (email or "").lower() in self.read_all()

    def role_of(self, email: str) -> str:
        """Return the user's role, or '' if not authorised."""
        rec = self.get(email)
        return rec.get("role", "") if rec else ""

    def is_admin(self, email: str) -> bool:
        """Return the admin flag; False for unknown users."""
        rec = self.get(email)
        return bool(rec.get("is_admin")) if rec else False

    # ── Internal: first-run env-var migration ──────────────────

    def _migrate_from_env(self) -> dict:
        """Bootstrap users.json from ALLOWED_EMAILS / ADMIN_EMAILS the
        FIRST time the store reads (no users.json present). Idempotent —
        if env vars are empty, returns {} and nothing is written."""
        allowed = [e.strip().lower() for e in
                   os.environ.get(_ALLOWED_ENV, "").split(",") if e.strip()]
        admins  = set(e.strip().lower() for e in
                      os.environ.get(_ADMINS_ENV, "").split(",") if e.strip())
        if not (allowed or admins):
            return {}
        now = datetime.now(timezone.utc).isoformat()
        users: dict = {}
        # Admins get role=manager + is_admin=true (default base role)
        for e in admins:
            users[e] = {"role": "manager", "is_admin": True,
                        "added_at": now, "added_by": "migration"}
        # Non-admin allowlist gets default role=support
        for e in allowed:
            if e in users:                                   # admin already set
                continue
            users[e] = {"role": DEFAULT_ROLE, "is_admin": False,
                        "added_at": now, "added_by": "migration"}
        if users:
            ok = self._put(USERS_KEY,
                           json.dumps(users, indent=2).encode(),
                           "application/json")
            if ok:
                log.info(f"users.json bootstrapped: {len(users)} users "
                         f"({len(admins)} admin)")
        return users
