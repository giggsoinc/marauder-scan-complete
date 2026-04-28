# =============================================================
# FILE: src/matcher/code_loader.py
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Load + validate code-deny and code-allow lists from S3.
#          Mirrors src/matcher/loader.py for the network side.
#          Merges baseline (Giggso) with custom (customer) so admin
#          edits via UI survive Docker image rebuilds.
# DEPENDS: rule_model, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Extracted from code_engine.py to honour 150-LOC cap.
# =============================================================

import logging
from typing import List, Tuple

import boto3

from .rule_model import parse_csv_text, dedupe, validate_code_rule

log = logging.getLogger("marauder-scan.matcher.code_loader")

UNAUTH_CODE_KEY        = "config/unauthorized_code.csv"
UNAUTH_CODE_CUSTOM_KEY = "config/unauthorized_code_custom.csv"
AUTH_CODE_KEY          = "config/authorized_code.csv"


def load_authorized_code(bucket: str, key: str = AUTH_CODE_KEY) -> list:
    """Backward-compat wrapper. Returns validated authorized_code rows only."""
    rows, _ = load_authorized_code_full(bucket, key)
    return rows


def load_authorized_code_full(bucket: str, key: str = AUTH_CODE_KEY) -> Tuple[List[dict], dict]:
    """Load + validate authorized_code.csv. Returns (rows, report)."""
    raw = _fetch(bucket, key)
    clean, errors = parse_csv_text(raw, validate_code_rule)
    if errors:
        log.warning("authorized_code.csv: %d invalid row(s) skipped", len(errors))
    log.info("Authorized code list: %d valid entries", len(clean))
    return clean, {"valid": len(clean), "errors": errors}


def load_unauthorized_code(bucket: str, key: str = UNAUTH_CODE_KEY) -> list:
    """Backward-compat wrapper. Returns the merged unauthorized_code rows only."""
    rows, _ = load_unauthorized_code_full(bucket, key)
    return rows


def load_unauthorized_code_full(bucket: str, key: str = UNAUTH_CODE_KEY) -> Tuple[List[dict], dict]:
    """
    Load baseline + custom code-deny lists. Validate via rule_model. Dedupe by pattern.
    Custom rows win on collision so customers can locally tighten severity.
    """
    base_raw   = _fetch(bucket, key)
    custom_raw = _fetch(bucket, UNAUTH_CODE_CUSTOM_KEY)
    base_clean, base_errs = parse_csv_text(base_raw,   validate_code_rule)
    cust_clean, cust_errs = parse_csv_text(custom_raw, validate_code_rule)
    merged = dedupe(base_clean + cust_clean, key_cols=("pattern",))
    if base_errs:
        log.warning("unauthorized_code.csv: %d invalid row(s) skipped", len(base_errs))
    if cust_errs:
        log.warning("unauthorized_code_custom.csv: %d invalid row(s) skipped", len(cust_errs))
    log.info(
        "Code deny list: baseline=%d custom=%d merged=%d",
        len(base_clean), len(cust_clean), len(merged),
    )
    return merged, {
        "baseline_valid":  len(base_clean),
        "baseline_errors": base_errs,
        "custom_valid":    len(cust_clean),
        "custom_errors":   cust_errs,
        "merged_count":    len(merged),
    }


def _fetch(bucket: str, key: str) -> str:
    """Fetch a CSV from S3 and return as string. Empty on miss/error."""
    try:
        s3 = boto3.client("s3")
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    except Exception as e:
        log.debug("Fetch %s failed (treated as absent): %s", key, e)
        return ""
