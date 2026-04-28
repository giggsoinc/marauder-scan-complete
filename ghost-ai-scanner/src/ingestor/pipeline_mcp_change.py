# =============================================================
# FILE: src/ingestor/pipeline_mcp_change.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Phase 1A. For each `mcp_server` finding the pipeline writes,
#          compare its `config_sha256` against the last known hash for
#          (device, mcp_host). If different, emit a derived
#          `mcp_config_changed` event with severity HIGH so the alerter
#          pages someone when an MCP config changes on a fleet device.
#          Extracted from pipeline.py to honour the 150-LOC cap.
# DEPENDS: store.findings_store
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A. Split out of pipeline.py.
# =============================================================

import logging

from store.findings_query import last_known_mcp_hash, record_mcp_hash

log = logging.getLogger("marauder-scan.ingestor.pipeline_mcp_change")


def maybe_emit_mcp_change(store, ev: dict) -> None:
    """For MCP-server events: if the SHA-256 of the parent config differs
    from the last hash we saw for (device, mcp_host), write a derived
    `mcp_config_changed` event and update the stored hash. No-op for
    non-MCP findings or when key fields are missing."""
    if ev.get("category") != "mcp_server":
        return
    device   = ev.get("src_hostname") or ev.get("email") or ""
    mcp_host = ev.get("mcp_host") or ""
    new_hash = ev.get("config_sha256") or ""
    if not (device and mcp_host and new_hash):
        return
    s3     = getattr(store.findings, "s3", None)
    bucket = getattr(store.findings, "bucket", "")
    if not (s3 and bucket):
        return
    last = last_known_mcp_hash(s3, bucket, device, mcp_host)
    if last and last != new_hash:
        change = dict(ev)
        change["category"] = "mcp_config_changed"
        change["outcome"]  = "MCP_CONFIG_CHANGED"
        change["severity"] = "HIGH"
        change["provider"] = f"mcp-change:{mcp_host}"
        change["notes"]    = f"hash {last[:8]} -> {new_hash[:8]}"
        try:
            store.findings.write(change)
        except Exception as e:
            log.warning(f"failed to write mcp_config_changed: {e}")
        log.info(f"MCP CHANGE on {device} [{mcp_host}]: "
                 f"{last[:8]} -> {new_hash[:8]}")
    record_mcp_hash(s3, bucket, device, mcp_host, new_hash)
