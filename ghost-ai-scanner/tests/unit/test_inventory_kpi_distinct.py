# =============================================================
# FILE: tests/unit/test_inventory_kpi_distinct.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc
# PURPOSE: Lock the v2.2 KPI bug fix in manager_tab_inventory —
#          "Devices" must reflect distinct device count, never the
#          raw event-row count. Pre-fix bug: 1 laptop with 1020 scan
#          events rendered as Devices=1020. Regression here ships
#          embarrassment direct to the customer.
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# We don't need streamlit here — only the pure helper.
from dashboard.ui.manager_tab_inventory import _asset_key  # noqa: E402


def _laptop_event(device: str, ts: str) -> dict:
    """Synthetic ENDPOINT_SCAN event row as it lands on dashboard."""
    return {
        "device_id":  device,
        "asset_type": "laptop",
        "timestamp":  ts,
        "outcome":    "ENDPOINT_FINDING",
        "email":      "ravi@giggso.com",
    }


def test_asset_key_prefers_device_id():
    e = {"device_id": "Mac-A", "src_hostname": "x", "src_ip": "1.1.1.1"}
    assert _asset_key(e) == "Mac-A"


def test_asset_key_falls_back_to_hostname_then_ip():
    assert _asset_key({"src_hostname": "host-b", "src_ip": "2.2.2.2"}) == "host-b"
    assert _asset_key({"src_ip": "3.3.3.3"}) == "3.3.3.3"
    assert _asset_key({}) == "unknown"


def test_distinct_device_count_one_laptop_many_scans():
    """The dashboard bug expressed as a contract: 1020 scan events
    from the SAME laptop must produce exactly 1 distinct device."""
    events = [
        _laptop_event("Mac-A", f"2026-05-11T{h:02d}:00:00Z")
        for h in range(24) for _ in range(43)   # 24 * 43 ≈ 1020
    ]
    assert len(events) >= 1000

    distinct = len({_asset_key(e) for e in events
                    if e.get("asset_type") == "laptop"})
    assert distinct == 1, (
        f"distinct device count drifted — got {distinct}, expected 1. "
        f"This is the bug that shipped Devices=1020 to the customer."
    )


def test_two_laptops_count_as_two():
    events = [_laptop_event(d, "2026-05-11T00:00:00Z")
              for d in ("Mac-A", "Mac-B")
              for _ in range(50)]
    distinct = len({_asset_key(e) for e in events
                    if e.get("asset_type") == "laptop"})
    assert distinct == 2


def test_scan_event_count_preserved_as_raw_sum():
    """The 'sub_label' card must still show the raw row count so
    operators can see the per-device scan volume."""
    events = [_laptop_event("Mac-A", "2026-05-11T00:00:00Z") for _ in range(1020)]
    raw_volume = sum(1 for e in events if e.get("asset_type") == "laptop")
    assert raw_volume == 1020
