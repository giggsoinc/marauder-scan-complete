# =============================================================
# FILE: src/matcher/__init__.py
# VERSION: 1.1.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Single entrypoint for the matcher package.
#          Loads CSVs from S3 on each scan cycle.
#          Returns a verdict for every normalised event.
# USAGE:
#   from matcher import match, load_unauthorized, load_authorized
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v1.1.0  2026-04-25  Group 6 — re-export rule_model + *_full() loader variants.
# =============================================================

from .engine    import match
from .loader    import (
    load_authorized, load_authorized_full,
    load_unauthorized, load_unauthorized_full,
)
from .code_loader import (
    load_authorized_code, load_authorized_code_full,
    load_unauthorized_code, load_unauthorized_code_full,
)
from .code_engine import CodeOutcome, triage as triage_code
from .outcomes  import Outcome
from .rule_model import (
    parse_csv_text, dedupe, find_conflicts,
    validate_rule, validate_allow_rule, validate_code_rule,
    normalize_domain, normalize_severity, is_too_broad, valid_glob,
    SEVERITIES, TOO_BROAD,
)

__all__ = [
    "match", "Outcome",
    "load_authorized", "load_authorized_full",
    "load_unauthorized", "load_unauthorized_full",
    "load_authorized_code", "load_authorized_code_full",
    "load_unauthorized_code", "load_unauthorized_code_full",
    "CodeOutcome", "triage_code",
    "parse_csv_text", "dedupe", "find_conflicts",
    "validate_rule", "validate_allow_rule", "validate_code_rule",
    "normalize_domain", "normalize_severity", "is_too_broad", "valid_glob",
    "SEVERITIES", "TOO_BROAD",
]
