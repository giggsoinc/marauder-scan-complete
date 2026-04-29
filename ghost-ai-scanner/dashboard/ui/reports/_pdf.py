# =============================================================
# FILE: dashboard/ui/reports/_pdf.py
# VERSION: 1.1.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: weasyprint wrapper — converts an HTML string to PDF bytes.
#          Called by reports_view.py after HTML preview is confirmed.
#          EC2 Debian 12 (Bookworm) system deps (Dockerfile installs):
#            libglib2.0-0t64 libpango-1.0-0 libpangocairo-1.0-0
#            libcairo2 libgdk-pixbuf-2.0-0 libharfbuzz0b fonts-dejavu-core
# DEPENDS: weasyprint>=62.0
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
#   v1.1.0  2026-04-29  Catch OSError on import (missing libgobject on
#                       Debian 12 Bookworm when libglib2.0-0t64 absent).
# =============================================================

import io
import logging

log = logging.getLogger("patronai.reports.pdf")

_WEASYPRINT_HINT = (
    "PDF unavailable — system library missing.\n"
    "On EC2: rebuild the Docker image (Dockerfile now includes libglib2.0-0t64).\n"
    "Locally: apt-get install -y libglib2.0-0t64 libpango-1.0-0 libcairo2 "
    "libgdk-pixbuf-2.0-0 libharfbuzz0b fonts-dejavu-core"
)


def html_to_pdf(html_str: str) -> bytes:
    """Convert an HTML string to PDF bytes via weasyprint.

    Returns PDF bytes on success.
    Raises RuntimeError with a user-friendly message on any failure
    so the Reports page shows a warning instead of crashing.
    """
    try:
        import weasyprint  # type: ignore
    except (ImportError, OSError) as exc:
        # OSError fires when weasyprint loads but libgobject-2.0 is absent
        log.error("weasyprint import failed: %s", exc)
        raise RuntimeError(_WEASYPRINT_HINT) from exc

    try:
        buf = io.BytesIO()
        weasyprint.HTML(string=html_str).write_pdf(buf)
        buf.seek(0)
        pdf_bytes = buf.read()
        log.info("PDF generated — %d bytes", len(pdf_bytes))
        return pdf_bytes
    except Exception as exc:
        log.error("PDF generation failed: %s", exc)
        raise RuntimeError(f"PDF generation failed: {exc}") from exc
