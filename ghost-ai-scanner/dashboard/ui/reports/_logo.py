# =============================================================
# FILE: dashboard/ui/reports/_logo.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Fetch company logo from S3 and return as base64 string
#          for embedding in report HTML (data: URI — no external
#          requests needed during PDF generation).
#          Path: s3://{bucket}/config/logo.png
# DEPENDS: boto3, base64
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import base64
import logging

log = logging.getLogger("patronai.reports.logo")

_LOGO_KEY = "config/logo.png"


def fetch_logo_b64(bucket: str, region: str = "us-east-1") -> str:
    """Fetch logo from S3 and return base64-encoded string.

    Returns empty string if bucket not set or object not found
    (report will render a grey placeholder box instead).
    """
    if not bucket:
        return ""
    try:
        import boto3
        obj = boto3.client("s3", region_name=region).get_object(
            Bucket=bucket, Key=_LOGO_KEY,
        )
        raw = obj["Body"].read()
        return base64.b64encode(raw).decode("utf-8")
    except Exception as exc:
        log.debug("Logo fetch skipped (%s) — placeholder will be used.", exc)
        return ""


def upload_logo(data: bytes, bucket: str,
                region: str = "us-east-1") -> bool:
    """Upload logo bytes to S3. Called from the Branding settings tab.

    Returns True on success, False on error.
    """
    if not bucket or not data:
        return False
    try:
        import boto3
        boto3.client("s3", region_name=region).put_object(
            Bucket=bucket,
            Key=_LOGO_KEY,
            Body=data,
            ContentType="image/png",
        )
        log.info("Logo uploaded to s3://%s/%s", bucket, _LOGO_KEY)
        return True
    except Exception as exc:
        log.error("Logo upload failed: %s", exc)
        return False
