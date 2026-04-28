# =============================================================
# FILE: src/blob_index_store.py
# VERSION: 1.1.0
# UPDATED: 2026-04-25
# PURPOSE: Coordinator. Single entry point for all persistence
#          operations. Imports and wires all store submodules.
#          Every other module imports this — not the submodules directly.
# OWNER: Ravi Venugopal, Giggso Inc
# USAGE:
#   store = BlobIndexStore(bucket="marauder-scan-company")
#   store.findings.write(finding)
#   store.dedup.is_duplicate(src_ip, provider)
#   store.cursor.write(last_key, file_count)
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial.
#   v1.1.0  2026-04-25  Step 0 — wire AgentStore so url_refresh_loop reaches it.
# =============================================================

from store.settings_store import SettingsStore
from store.cursor_store   import CursorStore
from store.findings_store import FindingsStore
from store.summary_store  import SummaryStore
from store.dedup_store    import DedupStore
from store.identity_store import IdentityStore
from store.report_store   import ReportStore
from store.agent_store    import AgentStore


class BlobIndexStore:
    """
    Single interface to all PatronAI persistence operations.
    Instantiate once in main.py. Pass to every module that needs storage.
    """

    def __init__(self, bucket: str, region: str = "us-east-1"):
        # Wire all stores to the same bucket and region
        self.settings = SettingsStore(bucket, region)
        self.cursor   = CursorStore(bucket, region)
        self.findings = FindingsStore(bucket, region)
        self.summary  = SummaryStore(bucket, region)
        self.dedup    = DedupStore(bucket, region)
        self.identity = IdentityStore(bucket, region)
        self.reports  = ReportStore(bucket, region)
        self.agent    = AgentStore(bucket, region)

        self.bucket = bucket
        self.region = region

    def __repr__(self) -> str:
        return f"BlobIndexStore(bucket={self.bucket}, region={self.region})"
