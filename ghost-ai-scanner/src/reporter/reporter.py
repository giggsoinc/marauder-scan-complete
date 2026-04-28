# =============================================================
# FILE: src/reporter/reporter.py
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Ravi Venugopal, Giggso Inc
# PURPOSE: Thin coordinator. Calls data_builder to gather data,
#          calls section builders to create PDF flowables,
#          assembles with ReportLab, writes to S3 via report_store,
#          returns pre-signed URL for Grafana download button.
# DEPENDS: reporter.data_builder, reporter.sections_*, blob_index_store
# =============================================================

import io
import logging
from datetime import date, timedelta

from reportlab.platypus  import SimpleDocTemplate
from reportlab.lib.pagesizes import letter
from reportlab.lib.units     import inch

from .data_builder    import build_summary, build_offenders, build_providers, build_events
from .sections_cover  import cover, executive_summary
from .sections_data   import top_offenders, provider_breakdown, event_log, residual_gaps

log     = logging.getLogger("marauder-scan.reporter")
MARGIN  = 0.75 * inch


class Reporter:
    """
    Generates PDF reports from scanner findings.
    Called on-demand from Grafana — never runs continuously.
    """

    def __init__(self, store, settings: dict):
        self._store   = store
        self._company = settings.get("company", {}).get("name", "Company")

    def generate(self, report_date: str = None, days: int = 7) -> str:
        """
        Generate PDF for the last N days.
        Returns pre-signed S3 URL or empty string on failure.
        """
        target     = report_date or date.today().isoformat()
        start_date = (date.today() - timedelta(days=days)).isoformat()
        date_range = f"{start_date} to {target}"

        log.info(f"Generating report: {date_range}")

        # Gather all data from store
        summary   = build_summary(self._store, days)
        offenders = build_offenders(self._store, days)
        providers = build_providers(self._store, days)
        events    = build_events(self._store, target)

        # Build PDF in memory
        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN,  bottomMargin=MARGIN,
            title=f"PatronAI Report — {self._company}",
            author="Giggso Inc (Ravi Venugopal)",
        )

        # Assemble flowables from section builders
        story = []
        story += cover(self._company, date_range)
        story += executive_summary(summary)
        story += top_offenders(offenders)
        story += provider_breakdown(providers)
        story += event_log(events)
        story += residual_gaps()

        try:
            doc.build(story)
        except Exception as e:
            log.error(f"PDF build failed: {e}")
            return ""

        pdf_bytes = buffer.getvalue()
        log.info(f"PDF built: {len(pdf_bytes):,} bytes")

        # Write to S3 — returns pre-signed URL
        return self._store.reports.write(pdf_bytes, target)
