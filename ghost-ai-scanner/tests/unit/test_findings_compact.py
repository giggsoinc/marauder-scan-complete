# =============================================================
# FILE: tests/unit/test_findings_compact.py
# VERSION: 1.0.0
# UPDATED: 2026-05-11
# OWNER: Giggso Inc
# PURPOSE: Lock the dashboard-noise fix.
#          The replay-21x test was Zaid's mandate from the Drama-mode
#          panel — feed the explode function the same scan blob 21
#          times and assert distinct findings == N_providers, not
#          21 * N_providers. Without this test, the v2.2 fix could
#          silently regress on any future refactor.
# DEPENDS: pytest, normalizer.agent_explode, jobs.findings_compact
# AUDIT LOG:
#   v1.0.0  2026-05-11  Initial.
# =============================================================

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from normalizer.agent_explode import explode_endpoint_findings, _finding_signature  # noqa: E402
from jobs.findings_compact import compact_day  # noqa: E402


def _bind_identity(event: dict, raw: dict) -> None:
    """Test stub for the identity binder normally injected by the
    pipeline. Just copy the device-identifying fields onto the event."""
    event["device_id"]   = raw.get("device_id", "")
    event["device_uuid"] = raw.get("device_uuid", "")
    event["email"]       = raw.get("email", "")
    event["src_ip"]      = raw.get("src_ip", "")


def _make_snapshot(provider_count: int = 5) -> dict:
    """Build one ENDPOINT_SCAN blob with `provider_count` synthetic
    findings — mimics the agent's 30-min payload."""
    findings = []
    for i in range(provider_count):
        findings.append({
            "type":   "process",
            "name":   f"ai-tool-{i}",
            "domain": "",
        })
    return {
        "token":       "tok-test",
        "company":     "acme",
        "device_id":   "MacBook-Pro-154.local",
        "device_uuid": "AAAA-BBBB-CCCC-DDDD",
        "email":       "ravi@giggso.com",
        "timestamp":   "2026-05-11T10:00:00+00:00",
        "scan_kind":   "recurring",
        "findings":    findings,
    }


# ── Part A — explode emits a signature ───────────────────────────────

def test_explode_emits_finding_signature():
    """Every emitted event must carry a stable finding_signature."""
    snap   = _make_snapshot(provider_count=3)
    events = explode_endpoint_findings(snap, "acme", _bind_identity)
    assert len(events) == 3
    for e in events:
        assert e.get("finding_signature"), "missing finding_signature on emitted event"
        assert len(e["finding_signature"]) == 16, "signature should be 16-char SHA-256 prefix"


def test_signature_stable_across_re_emissions():
    """Same snapshot replayed N times must produce identical signatures."""
    snap     = _make_snapshot(provider_count=5)
    run_a    = explode_endpoint_findings(snap, "acme", _bind_identity)
    run_b    = explode_endpoint_findings(snap, "acme", _bind_identity)
    sigs_a   = sorted(e["finding_signature"] for e in run_a)
    sigs_b   = sorted(e["finding_signature"] for e in run_b)
    assert sigs_a == sigs_b, "signatures drifted between identical replays"


def test_signature_changes_when_provider_changes():
    """Different provider on same device → different signature."""
    snap_a = _make_snapshot(provider_count=1)
    snap_b = _make_snapshot(provider_count=1)
    snap_b["findings"][0]["name"] = "different-tool"
    sig_a = explode_endpoint_findings(snap_a, "acme", _bind_identity)[0]["finding_signature"]
    sig_b = explode_endpoint_findings(snap_b, "acme", _bind_identity)[0]["finding_signature"]
    assert sig_a != sig_b


# ── Part B — Zaid's replay-21x mandate ──────────────────────────────

def test_replay_21_times_collapses_to_n_providers():
    """THE test. Replay the same snapshot 21 times (mimics 21 hourly
    scan cycles). After compaction, distinct signatures == N_providers,
    not 21*N. This is the contract that proves the dashboard will
    stop showing 1020 endpoints for a 1-laptop fleet."""
    snap = _make_snapshot(provider_count=5)
    all_events = []
    for _ in range(21):
        all_events.extend(explode_endpoint_findings(snap, "acme", _bind_identity))
    assert len(all_events) == 21 * 5, "explode itself should still emit per-cycle"

    distinct_sigs = {e["finding_signature"] for e in all_events}
    assert len(distinct_sigs) == 5, (
        f"expected 5 distinct signatures after 21 cycles × 5 providers, "
        f"got {len(distinct_sigs)} — dedup will break"
    )


# ── Part C — compact_day groups by signature ────────────────────────

class _StubDataFrame:
    """Minimal polars-DataFrame-shaped stub so compact_day can iterate."""
    def __init__(self, rows): self._rows = rows
    def is_empty(self): return not self._rows
    def iter_rows(self, named=True): return iter(self._rows)


class _StubFindingsStore:
    SEVERITY_FILES = ["critical", "high", "medium", "unknown"]
    def __init__(self, rows_by_sev):
        self._rows  = rows_by_sev
        self.writes = []
    def read(self, target_date, severity, limit=10_000):
        return _StubDataFrame(self._rows.get(severity, []))
    def _put(self, key, body, ctype):
        self.writes.append((key, body))
        return True


class _StubStore:
    def __init__(self, findings_store): self.findings = findings_store


def test_compact_day_groups_by_signature():
    """21 raw rows for the same signature → 1 compacted row with
    occurrences=21 and last_seen >= first_seen."""
    snap   = _make_snapshot(provider_count=1)
    events = []
    for hour in range(21):
        for ev in explode_endpoint_findings(snap, "acme", _bind_identity):
            ev["timestamp"] = f"2026-05-11T{hour:02d}:00:00+00:00"
            events.append(ev)
    fs    = _StubFindingsStore({"high": events})
    store = _StubStore(fs)

    summary = compact_day(store, "2026-05-11")
    assert summary["raw_rows"]   == 21
    assert summary["signatures"] == 1
    assert len(fs.writes) == 1
    body = fs.writes[0][1].decode().strip().splitlines()
    row  = json.loads(body[0])
    assert row["occurrences"] == 21
    assert row["first_seen"]  is not None
    assert row["last_seen"]   is not None
    assert row["first_seen"]  <= row["last_seen"]


def test_compact_day_auto_resolves_stale_signatures(monkeypatch):
    """A signature whose last_seen is older than STALE_CYCLES *
    SCAN_INTERVAL gets status=resolved, resolved_by=auto."""
    # Force a tight stale window so the test is deterministic.
    monkeypatch.setenv("AUTO_RESOLVE_STALE_CYCLES", "1")
    monkeypatch.setenv("SCAN_INTERVAL_SECS", "60")
    import importlib, jobs.findings_compact as fc
    importlib.reload(fc)

    snap = _make_snapshot(provider_count=1)
    ev   = explode_endpoint_findings(snap, "acme", _bind_identity)[0]
    ev["timestamp"] = "2020-01-01T00:00:00+00:00"   # ancient

    fs      = _StubFindingsStore({"high": [ev]})
    store   = _StubStore(fs)
    summary = fc.compact_day(store, "2020-01-01")

    assert summary["auto_resolved"] == 1
    body = fs.writes[0][1].decode().strip().splitlines()
    row  = json.loads(body[0])
    assert row["status"]      == "resolved"
    assert row["resolved_by"] == "auto"
