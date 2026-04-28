# =============================================================
# FILE: src/matcher/loader.py
# VERSION: 2.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Load deny + allow lists from S3, merge baseline (Giggso)
#          with customer custom lists, validate via rule_model, and
#          return clean rows + a load_report for diagnostics.
#          Reload on every scan cycle — no restart needed after edit.
# DEPENDS: rule_model, boto3
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v2.0.0  2026-04-25  Group 6 — rule_model validation + baseline/custom merge.
#                       Custom additions win on (domain,port) collision.
#                       Returns (rows, report) via *_full() variants.
# =============================================================

import logging
from typing import List, Tuple

import boto3

from .rule_model import (
    parse_csv_text, dedupe,
    validate_rule, validate_allow_rule,
)

log = logging.getLogger("marauder-scan.matcher.loader")

UNAUTH_KEY        = "config/unauthorized.csv"
UNAUTH_CUSTOM_KEY = "config/unauthorized_custom.csv"
AUTH_KEY          = "config/authorized.csv"


def load_authorized(bucket: str, key: str = AUTH_KEY) -> list:
    """Backward-compatible wrapper. Returns the validated allow-list rows only."""
    rows, _ = load_authorized_full(bucket, key)
    return rows


def load_authorized_full(bucket: str, key: str = AUTH_KEY) -> Tuple[List[dict], dict]:
    """Load + validate authorized.csv. Returns (rows, report) for UI/audit use."""
    raw = _fetch(bucket, key)
    clean, errors = parse_csv_text(raw, validate_allow_rule)
    if not raw:
        log.warning("authorized.csv missing — all suppress checks will fail")
    if errors:
        log.warning("authorized.csv: %d invalid row(s) skipped", len(errors))
    log.info("Allow list: %d valid entries", len(clean))
    return clean, {
        "total":  len(clean) + len(errors),
        "valid":  len(clean),
        "errors": errors,
    }


def load_unauthorized(bucket: str, key: str = UNAUTH_KEY) -> list:
    """Backward-compatible wrapper. Returns the merged deny-list rows only."""
    rows, _ = load_unauthorized_full(bucket, key)
    return rows


def load_unauthorized_full(bucket: str, key: str = UNAUTH_KEY) -> Tuple[List[dict], dict]:
    """
    Load baseline + custom deny lists, validate, dedupe, and return (rows, report).
    Custom rows win on (domain, port) collision so customers can tighten severity locally.
    """
    base_raw   = _fetch(bucket, key)
    custom_raw = _fetch(bucket, UNAUTH_CUSTOM_KEY)

    base_clean, base_errs   = parse_csv_text(base_raw,   validate_rule)
    cust_clean, cust_errs   = parse_csv_text(custom_raw, validate_rule)

    # Order matters: baseline first, custom appended → custom wins on dedup
    merged = dedupe(base_clean + cust_clean, key_cols=("domain", "port"))

    if not base_raw:
        log.error("unauthorized.csv missing — ghost AI detection running on custom list only")
    if base_errs:
        log.warning("unauthorized.csv: %d invalid row(s) skipped", len(base_errs))
    if cust_errs:
        log.warning("unauthorized_custom.csv: %d invalid row(s) skipped", len(cust_errs))

    log.info(
        "Deny list: baseline=%d custom=%d merged=%d",
        len(base_clean), len(cust_clean), len(merged),
    )

    return merged, {
        "baseline_total":  len(base_clean) + len(base_errs),
        "baseline_valid":  len(base_clean),
        "baseline_errors": base_errs,
        "custom_total":    len(cust_clean) + len(cust_errs),
        "custom_valid":    len(cust_clean),
        "custom_errors":   cust_errs,
        "merged_count":    len(merged),
    }


def _fetch(bucket: str, key: str) -> str:
    """Fetch a CSV from S3 and return as string. Empty string on miss/error."""
    try:
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read().decode("utf-8")
    except Exception as e:
        log.debug("Fetch %s failed (treated as absent): %s", key, e)
        return ""
