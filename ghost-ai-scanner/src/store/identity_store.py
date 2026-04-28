# =============================================================
# FILE: src/store/identity_store.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# PURPOSE: Load NAC CSV mapping from S3.
#          Used as last resort fallback in the 4-step identity chain.
#          Columns: ip, mac, username, department, location.
# OWNER: Ravi Venugopal, Giggso Inc
# DEPENDS: store.base_store, polars
# =============================================================

import io
import logging
import polars as pl
from .base_store import BaseStore

log = logging.getLogger("marauder-scan.identity_store")

NAC_KEY = "identity/nac-mapping.csv"

# Expected columns in the NAC CSV
REQUIRED_COLS = {"ip", "mac", "username"}
OPTIONAL_COLS = {"department", "location", "device_type"}


class IdentityStore(BaseStore):
    """
    Load and query the NAC IP-to-identity mapping CSV from S3.
    Polars used for fast in-memory lookup after initial load.
    """

    def _load_csv(self) -> pl.DataFrame:
        """Download and parse NAC CSV from S3 using Polars."""
        raw = self._get(NAC_KEY)
        if not raw:
            log.warning("NAC mapping CSV not found in S3. Identity fallback disabled.")
            return pl.DataFrame()
        try:
            df = pl.read_csv(io.BytesIO(raw))
            # Validate required columns present
            missing = REQUIRED_COLS - set(df.columns)
            if missing:
                log.error(f"NAC CSV missing required columns: {missing}")
                return pl.DataFrame()
            # Normalise IP column for consistent matching
            df = df.with_columns(pl.col("ip").str.strip_chars())
            log.info(f"NAC mapping loaded: {len(df)} entries")
            return df
        except Exception as e:
            log.error(f"Failed to parse NAC CSV: {e}")
            return pl.DataFrame()

    def lookup(self, src_ip: str) -> dict:
        """
        Look up an IP in the NAC mapping.
        Returns identity dict or empty dict if not found.
        """
        df = self._load_csv()
        if df.is_empty():
            return {}
        try:
            # Filter for matching IP
            match = df.filter(pl.col("ip") == src_ip)
            if match.is_empty():
                return {}
            row = match.row(0, named=True)
            return {
                "ip":          row.get("ip", src_ip),
                "mac":         row.get("mac", ""),
                "username":    row.get("username", ""),
                "department":  row.get("department", ""),
                "location":    row.get("location", ""),
                "device_type": row.get("device_type", ""),
                "source":      "nac_csv",
            }
        except Exception as e:
            log.error(f"NAC lookup failed for {src_ip}: {e}")
            return {}

    def all_ips(self) -> list:
        """Return all IPs in the NAC mapping. Used for bulk resolution."""
        df = self._load_csv()
        if df.is_empty():
            return []
        return df["ip"].to_list()

    def summary(self) -> dict:
        """Return NAC mapping stats for Streamlit settings dashboard."""
        df = self._load_csv()
        if df.is_empty():
            return {"loaded": False, "entries": 0}
        return {
            "loaded": True,
            "entries": len(df),
            "columns": df.columns,
            "departments": (
                df["department"].unique().to_list()
                if "department" in df.columns else []
            ),
        }
