# =============================================================
# FILE: src/store/base_store.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Shared base class for all store modules.
#          Initialises boto3 S3 client and bucket reference once.
#          Every store inherits this — no repeated setup code.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: boto3
# =============================================================

import logging
import boto3

log = logging.getLogger("marauder-scan.store")


class BaseStore:
    """
    Parent class for all store modules.
    Holds the S3 client and bucket name.
    Inherit this — get S3 for free.
    """

    def __init__(self, bucket: str, region: str = "us-east-1"):
        # Single S3 client shared across all methods in the subclass
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)
        self.region = region

    def _get(self, key: str) -> bytes:
        """Fetch raw bytes from S3. Returns empty bytes if key not found."""
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return b""
        except Exception as e:
            log.error(f"S3 get failed [{key}]: {e}")
            return b""

    def _put(self, key: str, body: bytes, content_type: str = "application/json") -> bool:
        """Write bytes to S3. Returns True on success."""
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            return True
        except Exception as e:
            log.error(f"S3 put failed [{key}]: {e}")
            return False

    def _exists(self, key: str) -> bool:
        """Check if a key exists in S3 without downloading it."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False
