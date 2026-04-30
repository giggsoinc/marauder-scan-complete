# =============================================================
# FILE: src/query/rollup_reader.py
# VERSION: 1.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Read hourly rollup files (written by jobs/hourly_rollup.py)
#          and merge a date-range into one dimension dict.
#          Two scopes:
#            - "user"   → users/{owner_hash16}/rollup/...
#            - "tenant" → tenants/{company_hash16}/rollup/...
#          Parallel S3 GETs, gzip-decoded, in-memory LRU.
# DEPENDS: boto3
# =============================================================

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3

log = logging.getLogger("marauder-scan.query.rollup_reader")

_BUCKET = os.environ.get("MARAUDER_SCAN_BUCKET", "")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_VALID_DIMS = {"provider", "user", "severity", "device", "category"}
_VALID_SCOPES = {"user", "tenant"}

_DEFAULT_MAX_WORKERS = 16
_CACHE_TTL_S = 300  # 5 minutes


# ── Hash + path ──────────────────────────────────────────────────


def _hash16(s: str) -> str:
    return hashlib.sha256((s or "").lower().encode()).hexdigest()[:16]


def _key(scope: str, scope_id: str, dim: str, t: datetime) -> str:
    base = ("users/"   + scope_id) if scope == "user" else ("tenants/" + scope_id)
    return (f"{base}/rollup/{t.year:04d}/{t.month:02d}/{t.day:02d}/{t.hour:02d}/"
            f"by_{dim}.json")


# ── In-memory LRU with TTL ──────────────────────────────────────


_cache_lock = threading.Lock()
_cache: dict[tuple, tuple[float, dict]] = {}


def _cache_get(key: tuple) -> Optional[dict]:
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        ts, val = entry
        if time.time() - ts > _CACHE_TTL_S:
            _cache.pop(key, None)
            return None
        return val


def _cache_put(key: tuple, val: dict) -> None:
    with _cache_lock:
        # naive size cap: drop the oldest 10% when over 256 entries.
        if len(_cache) > 256:
            for k in list(_cache.keys())[:32]:
                _cache.pop(k, None)
        _cache[key] = (time.time(), val)


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ── S3 fetch ────────────────────────────────────────────────────


def _s3():
    return boto3.client("s3", region_name=_REGION)


def _fetch_one(s3, key: str) -> dict:
    try:
        obj = s3.get_object(Bucket=_BUCKET, Key=key)
        body = obj["Body"].read()
        if obj.get("ContentEncoding") == "gzip" or key.endswith(".gz"):
            body = gzip.decompress(body)
        else:
            # Hourly rollups are gzip-compressed even though key has .json suffix
            # (we set ContentEncoding=gzip). boto3 may auto-decompress depending
            # on transfer config — handle both.
            try:
                body = gzip.decompress(body)
            except (OSError, gzip.BadGzipFile):
                pass
        return json.loads(body.decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        return {}
    except Exception as exc:
        log.debug("rollup fetch failed [%s]: %s", key, exc)
        return {}


# ── Merge logic per dimension ───────────────────────────────────


def _merge_provider(merged: dict, src: dict) -> None:
    """Merge two by_provider dicts. `users` is a sorted list of email strings;
    set-union for distinct counts."""
    for prov, entry in src.items():
        if prov not in merged:
            # Copy with users as a set internally for dedup.
            merged[prov] = {
                "hits": int(entry.get("hits", 0)),
                "_users": set(entry.get("users", []) or []),
                "device_count": int(entry.get("device_count", 0)),
                "categories": dict(entry.get("categories", {}) or {}),
                "by_severity": dict(entry.get("by_severity", {}) or {}),
                "first_seen": entry.get("first_seen", "") or "",
                "last_seen":  entry.get("last_seen",  "") or "",
            }
        else:
            m = merged[prov]
            m["hits"] += int(entry.get("hits", 0))
            m["_users"].update(entry.get("users", []) or [])
            m["device_count"] += int(entry.get("device_count", 0))
            for k, v in (entry.get("categories", {}) or {}).items():
                m["categories"][k] = m["categories"].get(k, 0) + int(v)
            for k, v in (entry.get("by_severity", {}) or {}).items():
                m["by_severity"][k] = m["by_severity"].get(k, 0) + int(v)
            fs = entry.get("first_seen", "")
            ls = entry.get("last_seen",  "")
            if fs and (not m["first_seen"] or fs < m["first_seen"]):
                m["first_seen"] = fs
            if ls and ls > m["last_seen"]:
                m["last_seen"] = ls


def _merge_user(merged: dict, src: dict) -> None:
    for u, entry in src.items():
        if u not in merged:
            merged[u] = {
                "hits": int(entry.get("hits", 0)),
                "_providers": set(entry.get("providers", []) or []),
                "device_count": int(entry.get("device_count", 0)),
                "categories": dict(entry.get("categories", {}) or {}),
                "by_severity": dict(entry.get("by_severity", {}) or {}),
                "total_risk": float(entry.get("total_risk", 0.0)),
                "first_seen": entry.get("first_seen", "") or "",
                "last_seen":  entry.get("last_seen",  "") or "",
            }
        else:
            m = merged[u]
            m["hits"] += int(entry.get("hits", 0))
            m["_providers"].update(entry.get("providers", []) or [])
            m["device_count"] += int(entry.get("device_count", 0))
            for k, v in (entry.get("categories", {}) or {}).items():
                m["categories"][k] = m["categories"].get(k, 0) + int(v)
            for k, v in (entry.get("by_severity", {}) or {}).items():
                m["by_severity"][k] = m["by_severity"].get(k, 0) + int(v)
            m["total_risk"] += float(entry.get("total_risk", 0.0))
            fs = entry.get("first_seen", "")
            ls = entry.get("last_seen",  "")
            if fs and (not m["first_seen"] or fs < m["first_seen"]):
                m["first_seen"] = fs
            if ls and ls > m["last_seen"]:
                m["last_seen"] = ls


def _merge_severity(merged: dict, src: dict) -> None:
    for k, v in src.items():
        merged[k] = merged.get(k, 0) + int(v)


def _merge_simple(merged: dict, src: dict) -> None:
    """device / category dimension merge."""
    for k, entry in src.items():
        if k not in merged:
            merged[k] = {
                "hits": int(entry.get("hits", 0)),
                "user_count": int(entry.get("user_count", 0)),
                "device_count": int(entry.get("device_count", 0)),
                "by_severity": dict(entry.get("by_severity", {}) or {}),
            }
        else:
            m = merged[k]
            m["hits"] += int(entry.get("hits", 0))
            m["user_count"] += int(entry.get("user_count", 0))
            m["device_count"] += int(entry.get("device_count", 0))
            for kk, vv in (entry.get("by_severity", {}) or {}).items():
                m["by_severity"][kk] = m["by_severity"].get(kk, 0) + int(vv)


def _finalise(dim: str, merged: dict) -> dict:
    """Convert internal sets back to counts/sorted lists for JSON output."""
    if dim == "provider":
        out = {}
        for prov, m in merged.items():
            users = sorted(m.pop("_users"))
            m["users"] = users
            m["user_count"] = len(users)
            out[prov] = m
        return out
    if dim == "user":
        out = {}
        for u, m in merged.items():
            provs = sorted(m.pop("_providers"))
            m["providers"] = provs
            m["provider_count"] = len(provs)
            out[u] = m
        return out
    return merged


# ── Public API ──────────────────────────────────────────────────


def _hours_in_range(start: datetime, end: datetime) -> list[datetime]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.replace(minute=0, second=0, microsecond=0)
    end   = end.replace(minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    cur = start
    while cur < end:
        out.append(cur)
        cur += timedelta(hours=1)
    return out


def read_dimension_range(scope: str, scope_id: str, dimension: str,
                         start: datetime, end: datetime,
                         max_workers: int = _DEFAULT_MAX_WORKERS) -> dict:
    """Read & merge by_<dimension>.json for every hour in [start, end)
    under the given scope. Returns the merged dimension dict.

    Args:
        scope:     "user" | "tenant"
        scope_id:  16-char hex hash (compute via hash_email() / hash_company())
        dimension: provider | user | severity | device | category
        start:     window start (UTC)
        end:       window end   (UTC, exclusive)
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}")
    if dimension not in _VALID_DIMS:
        raise ValueError(f"invalid dimension {dimension!r}")
    if not _BUCKET:
        log.warning("read_dimension_range: bucket not set")
        return {}

    cache_key = (scope, scope_id, dimension,
                 start.replace(tzinfo=timezone.utc).isoformat() if start.tzinfo is None else start.isoformat(),
                 end.replace(tzinfo=timezone.utc).isoformat()   if end.tzinfo   is None else end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    hours = _hours_in_range(start, end)
    if not hours:
        return {}

    s3 = _s3()
    keys = [_key(scope, scope_id, dimension, t) for t in hours]

    merged: dict = {} if dimension != "severity" else {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_one, s3, k): k for k in keys}
        for fut in as_completed(futures):
            payload = fut.result()
            if not payload:
                continue
            if dimension == "provider":
                _merge_provider(merged, payload)
            elif dimension == "user":
                _merge_user(merged, payload)
            elif dimension == "severity":
                _merge_severity(merged, payload)
            else:  # device, category
                _merge_simple(merged, payload)

    final = _finalise(dimension, merged)
    _cache_put(cache_key, final)
    return final


# ── Convenience wrappers ────────────────────────────────────────


def hash_email(email: str) -> str:
    return _hash16(email)


def hash_company(company: str) -> str:
    return _hash16(company)


def scope_for_view(view: str) -> str:
    """Map dashboard view to rollup scope.
    exec → user (own data) ; manager/support/home → tenant (team-wide)."""
    return "user" if view == "exec" else "tenant"


def resolve_scope_id(view: str, email: str, company: str) -> str:
    """Return the right hash for the chosen scope."""
    if view == "exec":
        return hash_email(email)
    return hash_company(company)


def default_window(days_back: int = 30) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=max(1, int(days_back)))
    return start, end
