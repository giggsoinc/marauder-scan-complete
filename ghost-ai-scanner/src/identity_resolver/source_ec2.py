# =============================================================
# FILE: src/identity_resolver/source_ec2.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Resolve source IP to owner via EC2 instance Name tags.
#          Fastest source — direct EC2 API call on private IP.
#          Requires Owner and Department tags set on all instances.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: boto3
# =============================================================

import logging
from typing import Optional
import boto3
from .sources import make_identity

log = logging.getLogger("marauder-scan.identity_resolver.ec2")


def resolve(ip: str, region: str = "us-east-1") -> Optional[dict]:
    """
    Look up private IP in EC2 describe_instances.
    Returns identity dict if Owner tag found, else None.
    """
    try:
        ec2  = boto3.client("ec2", region_name=region)
        resp = ec2.describe_instances(
            Filters=[{"Name": "private-ip-address", "Values": [ip]}]
        )
        for reservation in resp.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                tags  = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
                owner = tags.get("Owner") or tags.get("employee_id", "")
                if not owner:
                    continue
                return make_identity(
                    ip=ip,
                    source="ec2_tags",
                    owner=owner,
                    department=tags.get("Department", ""),
                    email=tags.get("Email", ""),
                    asset_type=instance.get("InstanceType", "ec2"),
                )
    except Exception as e:
        log.debug(f"EC2 tag lookup failed for {ip}: {e}")
    return None
