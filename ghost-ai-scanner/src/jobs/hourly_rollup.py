# =============================================================
# FILE: src/jobs/hourly_rollup.py
# VERSION: 1.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Hourly aggregation of findings/YYYY/MM/DD/{sev}.jsonl into
#          small dimension files at TWO scopes:
#            users/{owner_hash16}/rollup/YYYY/MM/DD/HH/by_*.json
#            tenants/{company_hash16}/rollup/YYYY/MM/DD/HH/by_*.json
#          Lets chat tools answer at any time-window with O(hours)
#          small reads instead of O(events) raw scan.
# DEPENDS: store.findings_store (read), store.base_store (write),
#          normalizer.provider_names (human AI-tool names), boto3
# USAGE:
#   python -m src.jobs.hourly_rollup --catch-up
#   python -m src.jobs.hourly_rollup --backfill --start 2026-01-01T00 --end 2026-04-29T00
#   python -m src.jobs.hourly_rollup --hour 2026-04-29T15
# =============================================================

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import boto3

# Make sibling src modules importable when run as a script.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from normalizer.provider_names import normalize_provider, is_known  # noqa: E402

log = logging.getLogger("marauder-scan.jobs.hourly_rollup")

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_SEVERITIES = ["critical", "high", "medium", "unknown"]
_DIMENSIONS = ["provider", "user", "severity", "device", "category"]


# ── Path helpers ─────────────────────────────────────────────────


def _hash16(s: str) -> str:
    return hashlib.sha256((s or "").lower().encode()).hexdigest()[:16]


def _findings_key(d: datetime, severity: str) -> str:
    return f"findings/{d.year:04d}/{d.month:02d}/{d.day:02d}/{severity}.jsonl"


def _rollup_prefix_user(owner_hash: str, d: datetime) -> str:
    return (f"users/{owner_hash}/rollup/"
            f"{d.year:04d}/{d.month:02d}/{d.day:02d}/{d.hour:02d}/")


def _rollup_prefix_tenant(company_hash: str, d: datetime) -> str:
    return (f"tenants/{company_hash}/rollup/"
            f"{d.year:04d}/{d.month:02d}/{d.day:02d}/{d.hour:02d}/")


# ── Aggregator ───────────────────────────────────────────────────


def _empty_provider_entry() -> dict:
    return {"hits": 0, "_users": set(), "_devices": set(),
            "categories": defaultdict(int), "by_severity": defaultdict(int),
            "first_seen": "", "last_seen": ""}


def _empty_user_entry() -> dict:
    return {"hits": 0, "_providers": set(), "_devices": set(),
            "categories": defaultdict(int), "by_severity": defaultdict(int),
            "total_risk": 0.0, "first_seen": "", "last_seen": ""}


def _empty_simple_entry() -> dict:
    return {"hits": 0, "_users": set(), "_devices": set(),
            "by_severity": defaultdict(int)}


_SEVERITY_RISK = {"CRITICAL": 5.0, "HIGH": 3.0, "MEDIUM": 1.5,
                  "LOW": 0.5, "UNKNOWN": 0.5}


class _ScopeAgg:
    """Holds the 5 dimension dicts for one scope (one user OR one tenant)."""

    def __init__(self) -> None:
        self.by_provider: dict = defaultdict(_empty_provider_entry)
        self.by_user:     dict = defaultdict(_empty_user_entry)
        self.by_severity: dict = defaultdict(int)
        self.by_device:   dict = defaultdict(_empty_simple_entry)
        self.by_category: dict = defaultdict(_empty_simple_entry)
        self.rows: int = 0

    def add(self, row: dict) -> None:
        self.rows += 1
        prov_raw = row.get("provider") or ""
        category = row.get("category") or ""
        severity = (row.get("severity") or "UNKNOWN").upper()
        owner    = (row.get("owner") or row.get("email") or "unknown").lower()
        device   = row.get("src_hostname") or row.get("device_uuid") or ""
        ts       = row.get("timestamp") or ""

        # Severity → simple counter.
        self.by_severity[severity] += 1

        # Provider dimension — normalize to human name.
        if prov_raw:
            prov = normalize_provider(category, prov_raw)
            p = self.by_provider[prov]
            p["hits"] += 1
            p["_users"].add(owner)
            if device:
                p["_devices"].add(device)
            p["categories"][category] += 1
            p["by_severity"][severity] += 1
            if ts and (not p["first_seen"] or ts < p["first_seen"]):
                p["first_seen"] = ts
            if ts and ts > p["last_seen"]:
                p["last_seen"] = ts

        # User dimension.
        u = self.by_user[owner]
        u["hits"] += 1
        if prov_raw:
            u["_providers"].add(normalize_provider(category, prov_raw))
        if device:
            u["_devices"].add(device)
        u["categories"][category] += 1
        u["by_severity"][severity] += 1
        u["total_risk"] += _SEVERITY_RISK.get(severity, 0.5)
        if ts and (not u["first_seen"] or ts < u["first_seen"]):
            u["first_seen"] = ts
        if ts and ts > u["last_seen"]:
            u["last_seen"] = ts

        # Device dimension.
        if device:
            d = self.by_device[device]
            d["hits"] += 1
            d["_users"].add(owner)
            d["by_severity"][severity] += 1

        # Category dimension.
        if category:
            c = self.by_category[category]
            c["hits"] += 1
            c["_users"].add(owner)
            if device:
                c["_devices"].add(device)
            c["by_severity"][severity] += 1

    # ── Serialisation ────────────────────────────────────────────

    @staticmethod
    def _finalise_provider(p: dict) -> dict:
        return {"hits": p["hits"],
                "users": sorted(p["_users"]),
                "user_count": len(p["_users"]),
                "device_count": len(p["_devices"]),
                "categories": dict(p["categories"]),
                "by_severity": dict(p["by_severity"]),
                "first_seen": p["first_seen"],
                "last_seen": p["last_seen"]}

    @staticmethod
    def _finalise_user(u: dict) -> dict:
        return {"hits": u["hits"],
                "providers": sorted(u["_providers"]),
                "device_count": len(u["_devices"]),
                "categories": dict(u["categories"]),
                "by_severity": dict(u["by_severity"]),
                "total_risk": round(u["total_risk"], 2),
                "first_seen": u["first_seen"],
                "last_seen": u["last_seen"]}

    @staticmethod
    def _finalise_simple(s: dict) -> dict:
        return {"hits": s["hits"],
                "user_count": len(s["_users"]),
                "device_count": len(s.get("_devices", [])) if "_devices" in s else 0,
                "by_severity": dict(s["by_severity"])}

    def serialise(self) -> dict[str, dict]:
        return {
            "by_provider": {k: self._finalise_provider(v)
                            for k, v in self.by_provider.items()},
            "by_user":     {k: self._finalise_user(v)
                            for k, v in self.by_user.items()},
            "by_severity": dict(self.by_severity),
            "by_device":   {k: self._finalise_simple(v)
                            for k, v in self.by_device.items()},
            "by_category": {k: self._finalise_simple(v)
                            for k, v in self.by_category.items()},
        }


# ── S3 helpers ──────────────────────────────────────────────────


def _s3():
    return boto3.client("s3", region_name=_REGION)


def _put_gz(s3, key: str, payload: dict) -> None:
    body = gzip.compress(json.dumps(payload, default=str).encode("utf-8"))
    s3.put_object(Bucket=_BUCKET, Key=key, Body=body,
                  ContentType="application/json",
                  ContentEncoding="gzip")


def _select_rows_for_window(s3, key: str, window_start: datetime,
                            window_end: datetime) -> Iterable[dict]:
    """S3 Select rows in [window_start, window_end). Pushes timestamp filter
    to S3 so we never download out-of-window events. Falls back to GetObject
    on Select failure (e.g. mixed-schema parse errors) — degraded but works."""
    iso_start = window_start.isoformat()
    iso_end   = window_end.isoformat()
    sql = (f"SELECT s.provider, s.category, s.severity, s.owner, s.email, "
           f"s.src_hostname, s.device_uuid, s.timestamp, s.company "
           f"FROM s3object s "
           f"WHERE s.timestamp >= '{iso_start}' AND s.timestamp < '{iso_end}'")
    try:
        resp = s3.select_object_content(
            Bucket=_BUCKET, Key=key, ExpressionType="SQL", Expression=sql,
            InputSerialization={"JSON": {"Type": "LINES"}, "CompressionType": "NONE"},
            OutputSerialization={"JSON": {"RecordDelimiter": "\n"}},
        )
        for ev in resp["Payload"]:
            if "Records" not in ev:
                continue
            chunk = ev["Records"]["Payload"].decode()
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except s3.exceptions.NoSuchKey:
        return
    except Exception as exc:
        log.warning("S3 Select failed on %s: %s — falling back to GetObject", key, exc)
        try:
            obj = s3.get_object(Bucket=_BUCKET, Key=key)
            for line in obj["Body"].iter_lines():
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("timestamp", "")
                if iso_start <= ts < iso_end:
                    yield row
        except s3.exceptions.NoSuchKey:
            return
        except Exception as exc2:
            log.error("Fallback GetObject also failed on %s: %s", key, exc2)


# ── Top-level: compute + write one hour ─────────────────────────


def compute_hourly_rollup(window_start: datetime,
                          window_end: Optional[datetime] = None) -> dict:
    """Aggregate the hour [window_start, window_end) and write rollup files.
    Default end is window_start + 1 hour. Idempotent."""
    if not _BUCKET:
        log.warning("compute_hourly_rollup: MARAUDER_SCAN_BUCKET not set; skipping")
        return {"skipped": True}

    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end is None:
        window_end = window_start + timedelta(hours=1)
    elif window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)

    s3 = _s3()
    started = time.time()
    log.info("rollup: window %s → %s", window_start.isoformat(), window_end.isoformat())

    # Build aggregators per scope.
    user_aggs:   dict[str, _ScopeAgg] = defaultdict(_ScopeAgg)
    tenant_aggs: dict[str, _ScopeAgg] = defaultdict(_ScopeAgg)
    user_emails:  dict[str, str] = {}    # hash → original email (lowercased)
    tenant_names: dict[str, str] = {}    # hash → company name
    rows_total = 0
    unknown_providers: set[tuple[str, str]] = set()

    # The hour window may span two daily files if window crosses UTC midnight.
    # We process every day touched by [start, end) and re-filter in S3 Select.
    cur = window_start.replace(minute=0, second=0, microsecond=0)
    days_seen: set[str] = set()
    while cur < window_end:
        day_key = cur.strftime("%Y-%m-%d")
        if day_key not in days_seen:
            days_seen.add(day_key)
            for sev in _SEVERITIES:
                key = _findings_key(cur, sev)
                for row in _select_rows_for_window(s3, key, window_start, window_end):
                    rows_total += 1
                    owner = (row.get("owner") or row.get("email") or "unknown").lower()
                    company = row.get("company") or ""
                    o_hash = _hash16(owner)
                    c_hash = _hash16(company)
                    user_emails[o_hash]  = owner
                    tenant_names[c_hash] = company
                    user_aggs[o_hash].add(row)
                    tenant_aggs[c_hash].add(row)

                    prov_raw = row.get("provider") or ""
                    cat      = row.get("category") or ""
                    if prov_raw and not is_known(cat, prov_raw):
                        unknown_providers.add((cat, prov_raw))
        cur += timedelta(hours=1)

    completed = time.time()

    # Write per-user rollups.
    for o_hash, agg in user_aggs.items():
        prefix = _rollup_prefix_user(o_hash, window_start)
        ser = agg.serialise()
        # Drop by_user — redundant in per-user scope; the user IS the scope.
        ser.pop("by_user", None)
        for dim, payload in ser.items():
            _put_gz(s3, prefix + f"by_{dim}.json", payload)
        _put_gz(s3, prefix + "_meta.json", {
            "scope": "user",
            "owner_hash": o_hash,
            "owner_email": user_emails.get(o_hash, ""),
            "window_start": window_start.isoformat(),
            "window_end":   window_end.isoformat(),
            "rows": agg.rows,
            "run_started_at":   datetime.fromtimestamp(started,   tz=timezone.utc).isoformat(),
            "run_completed_at": datetime.fromtimestamp(completed, tz=timezone.utc).isoformat(),
        })

    # Write per-tenant rollups.
    for c_hash, agg in tenant_aggs.items():
        prefix = _rollup_prefix_tenant(c_hash, window_start)
        for dim, payload in agg.serialise().items():
            _put_gz(s3, prefix + f"by_{dim}.json", payload)
        _put_gz(s3, prefix + "_meta.json", {
            "scope": "tenant",
            "company_hash": c_hash,
            "company_name": tenant_names.get(c_hash, ""),
            "window_start": window_start.isoformat(),
            "window_end":   window_end.isoformat(),
            "rows": agg.rows,
            "users": len(agg.by_user),
            "run_started_at":   datetime.fromtimestamp(started,   tz=timezone.utc).isoformat(),
            "run_completed_at": datetime.fromtimestamp(completed, tz=timezone.utc).isoformat(),
        })

    # Append unknown providers to a single audit file (best-effort).
    if unknown_providers:
        _append_unknown_providers(s3, unknown_providers)

    log.info("rollup: window %s done — %d rows, %d users, %d tenants in %.1fs",
             window_start.isoformat(), rows_total, len(user_aggs),
             len(tenant_aggs), completed - started)
    return {"rows": rows_total, "users": len(user_aggs),
            "tenants": len(tenant_aggs),
            "unknown_providers": len(unknown_providers),
            "duration_s": completed - started}


def _append_unknown_providers(s3, unknowns: set[tuple[str, str]]) -> None:
    key = "rollup-meta/unknown_providers.jsonl"
    try:
        try:
            existing = s3.get_object(Bucket=_BUCKET, Key=key)["Body"].read().decode()
        except s3.exceptions.NoSuchKey:
            existing = ""
        ts = datetime.now(timezone.utc).isoformat()
        new_lines = "\n".join(
            json.dumps({"ts": ts, "category": c, "raw_provider": p})
            for c, p in sorted(unknowns)
        )
        body = (existing.rstrip("\n") + "\n" + new_lines).lstrip("\n").encode()
        s3.put_object(Bucket=_BUCKET, Key=key, Body=body,
                      ContentType="application/x-ndjson")
    except Exception as exc:
        log.debug("unknown_providers append failed (non-fatal): %s", exc)


# ── Catch-up + backfill ─────────────────────────────────────────


def _hour_floor(t: datetime) -> datetime:
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.replace(minute=0, second=0, microsecond=0)


def _latest_completed_hour(s3) -> Optional[datetime]:
    """Find latest tenants/*/rollup/.../HH/_meta.json. Returns None if empty."""
    try:
        paginator = s3.get_paginator("list_objects_v2")
        latest: Optional[datetime] = None
        for page in paginator.paginate(Bucket=_BUCKET, Prefix="tenants/"):
            for obj in page.get("Contents", []):
                k = obj["Key"]
                if not k.endswith("/_meta.json"):
                    continue
                # Path: tenants/{hash}/rollup/YYYY/MM/DD/HH/_meta.json
                parts = k.split("/")
                try:
                    yyyy, mm, dd, hh = parts[3], parts[4], parts[5], parts[6]
                    t = datetime(int(yyyy), int(mm), int(dd), int(hh),
                                 tzinfo=timezone.utc)
                    if latest is None or t > latest:
                        latest = t
                except (IndexError, ValueError):
                    continue
        return latest
    except Exception as exc:
        log.warning("latest_completed_hour scan failed: %s", exc)
        return None


def catch_up_rollups(max_hours: int = 720) -> int:
    """Process every missing hour from latest-completed up to now-1h.
    Bounded by max_hours (30 days default) so a long outage doesn't loop
    forever.  When no rollups exist at all (fresh deploy), backfill the
    last `ROLLUP_INITIAL_BACKFILL_DAYS` (env, default 7) — otherwise the
    chat would see empty rollups for any historical window and the LLM
    would (correctly) report no data, even when raw findings exist.
    Returns count of hours processed."""
    if not _BUCKET:
        return 0
    s3 = _s3()
    target_end = _hour_floor(datetime.now(timezone.utc))  # exclusive
    start = _latest_completed_hour(s3)
    if start is None:
        initial_days = int(os.environ.get("ROLLUP_INITIAL_BACKFILL_DAYS", "7"))
        start = target_end - timedelta(days=max(1, initial_days))
        log.info("catch_up_rollups: fresh deploy — backfilling last %d days "
                 "(%s → %s)", initial_days, start.isoformat(),
                 target_end.isoformat())
    else:
        start = start + timedelta(hours=1)

    processed = 0
    cur = start
    while cur < target_end and processed < max_hours:
        try:
            compute_hourly_rollup(cur)
        except Exception as exc:
            log.error("catch_up: hour %s failed: %s", cur.isoformat(), exc)
        cur += timedelta(hours=1)
        processed += 1
    log.info("catch_up_rollups: processed %d hours up to %s",
             processed, target_end.isoformat())
    return processed


def backfill(start: datetime, end: datetime) -> int:
    """Process every hour in [start, end). Returns count processed."""
    cur = _hour_floor(start)
    end = _hour_floor(end)
    n = 0
    while cur < end:
        try:
            compute_hourly_rollup(cur)
            n += 1
        except Exception as exc:
            log.error("backfill hour %s failed: %s", cur.isoformat(), exc)
        cur += timedelta(hours=1)
    return n


# ── Scheduler thread ─────────────────────────────────────────────


def scheduler_loop(stop_event, offset_minutes: int = 5) -> None:
    """Run forever. At HH:offset every hour, compute the hour that just ended.
    Fires catch_up_rollups once on startup so missing hours are filled.
    Safe to run as a daemon thread alongside scanner_loop."""
    if not _BUCKET:
        log.warning("scheduler_loop: bucket not set — exiting")
        return

    log.info("scheduler_loop: starting (offset=:%02d, catch-up first)", offset_minutes)
    try:
        catch_up_rollups()
    except Exception as exc:
        log.error("startup catch-up failed (non-fatal): %s", exc)

    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        # Next firing: top of the next hour + offset.
        nxt = (now.replace(minute=0, second=0, microsecond=0)
               + timedelta(hours=1, minutes=offset_minutes))
        sleep_s = max(30, (nxt - now).total_seconds())
        if stop_event.wait(timeout=sleep_s):
            return
        # Process the previous full hour [H-1:00, H:00).
        target = (datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
                  - timedelta(hours=1))
        try:
            compute_hourly_rollup(target)
        except Exception as exc:
            log.error("scheduled rollup for %s failed: %s", target.isoformat(), exc)


# ── CLI ──────────────────────────────────────────────────────────


def _parse_iso_hour(s: str) -> datetime:
    # Accept 2026-04-29T15 or 2026-04-29T15:00 or full ISO.
    fmts = ["%Y-%m-%dT%H", "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise SystemExit(f"unparseable hour: {s}")


def main(argv: Optional[list] = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    p = argparse.ArgumentParser(description="PatronAI hourly rollup job")
    p.add_argument("--hour", type=str, help="Single hour to process (UTC)")
    p.add_argument("--catch-up", action="store_true",
                   help="Fill all missing hours from latest-completed up to now-1h")
    p.add_argument("--backfill", action="store_true",
                   help="Process every hour in [--start, --end)")
    p.add_argument("--start", type=str, help="Backfill start (UTC)")
    p.add_argument("--end",   type=str, help="Backfill end (UTC, exclusive)")
    args = p.parse_args(argv)

    if args.hour:
        compute_hourly_rollup(_parse_iso_hour(args.hour))
    elif args.catch_up:
        catch_up_rollups()
    elif args.backfill:
        if not args.start or not args.end:
            p.error("--backfill requires --start and --end")
        n = backfill(_parse_iso_hour(args.start), _parse_iso_hour(args.end))
        log.info("backfill: %d hours processed", n)
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
