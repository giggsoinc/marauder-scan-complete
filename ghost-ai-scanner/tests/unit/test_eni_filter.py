# =============================================================
# FILE: tests/unit/test_eni_filter.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Unit tests for ENI denylist filter.
#          Covers all 5 deny rule types, the keep (EC2) case,
#          and the cache-miss fail-open path.
#          No AWS calls — pure dict inputs.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — 7 test cases
# =============================================================

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from normalizer.eni_filter import is_denied_eni, load_eni_patterns

# Load real patterns from config — tests run from repo root or tests/unit/
_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "../../config/eni_denylist.yaml"
)
PATTERNS = load_eni_patterns(_CONFIG_PATH)

ACCOUNT_ID = "324037322652"


def _meta(description="", interface_type="interface",
          requester_managed=False, requester_id="", owner_id=ACCOUNT_ID) -> dict:
    """Build a minimal ENI metadata dict matching describe_network_interfaces output."""
    return {
        "Description":      description,
        "InterfaceType":    interface_type,
        "RequesterManaged": requester_managed,
        "RequesterId":      requester_id,
        "OwnerId":          owner_id,
    }


def test_efs_denied_by_description():
    """EFS ENI matched by description prefix must be denied."""
    meta = _meta(
        description="EFS mount target for fs-0aa9f0a411ce090be",
        requester_managed=True,
    )
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "efs"


def test_efs_denied_by_requester_id():
    """EFS ENI matched by AWS EFS service requester ID must be denied."""
    meta = _meta(requester_managed=True, requester_id="641247547298")
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "efs"


def test_nat_gateway_denied():
    """NAT Gateway ENI matched by interface_type must be denied."""
    meta = _meta(interface_type="nat_gateway", requester_managed=True)
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "nat"


def test_vpc_endpoint_denied():
    """VPC Endpoint ENI matched by interface_type must be denied."""
    meta = _meta(interface_type="vpc_endpoint", requester_managed=True)
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "vpce"


def test_elb_denied_by_description():
    """Load Balancer ENI matched by ELB description prefix must be denied."""
    meta = _meta(
        description="ELB app/my-alb/abc123def456",
        requester_managed=True,
    )
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "elb"


def test_lambda_idle_eni_denied():
    """Lambda idle ENI matched by description prefix must be denied."""
    meta = _meta(
        description="AWS Lambda VPC ENI-my-function-abc123",
        requester_managed=True,
    )
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is True
    assert reason == "lambda"


def test_customer_ec2_eni_kept():
    """Customer-owned EC2 ENI must pass through — not denied."""
    meta = _meta(
        description="",
        interface_type="interface",
        requester_managed=False,
        owner_id=ACCOUNT_ID,
    )
    denied, reason = is_denied_eni(meta, PATTERNS, ACCOUNT_ID)
    assert denied is False
    assert reason == ""


def test_cache_miss_fail_open():
    """Empty metadata (cache miss) must fail open — never drop unclassified flows."""
    denied, reason = is_denied_eni({}, PATTERNS, ACCOUNT_ID)
    assert denied is False
    assert reason == ""
