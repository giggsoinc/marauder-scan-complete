# =============================================================
# FILE: dashboard/ui/helpers.py
# VERSION: 2.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Shared constants and micro-helpers for the PatronAI UI.
#          SEV_COLOURS, Plotly base config, badge and flag renderers.
#          v2 sources colors from theme.py (light theme).
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — extracted from ghost_dashboard.py
#   v2.0.0  2026-04-27  Light theme — PLOTLY_BASE delegates to
#                       theme.plotly_layout(); SEV_COLOURS rebased.
#   v2.1.0  2026-04-27  sev_badge adds icons (🔴/🟡/🔵/🚨); geo_flag
#                       extended. Imports SEV_ICON from theme.
# =============================================================

from .theme import (
    SEV, SEV_ICON, TEXT_VALUE, TEXT_MUTED, TEXT_LINK,
    BG_CARD, plotly_layout,
)

# Legacy color map (kept for callers that still import it) — now points
# at the LIGHT-theme severity foreground hexes.
SEV_COLOURS: dict = {
    "CRITICAL": SEV["CRITICAL"][0],
    "HIGH":     SEV["HIGH"][0],
    "MEDIUM":   SEV["MEDIUM"][0],
    "LOW":      SEV["LOW"][0],
    "UNKNOWN":  SEV["UNKNOWN"][0],
    "CLEAN":    SEV["CLEAN"][0],
}

# Backwards-compatible PLOTLY_BASE — delegated to theme.plotly_layout()
# so all charts pick up the light template + palette in one place.
PLOTLY_BASE: dict = plotly_layout()

PLOTLY_CONFIG: dict = dict(displayModeBar=False, responsive=True)

_FLAGS: dict = {
    "USA": "🇺🇸", "UK": "🇬🇧", "Germany": "🇩🇪", "India": "🇮🇳",
    "China": "🇨🇳", "Russia": "🇷🇺", "France": "🇫🇷", "Canada": "🇨🇦",
    "Australia": "🇦🇺", "Brazil": "🇧🇷", "Internal": "🏢",
}

COUNTRY_ISO: dict = {
    "USA": "USA", "UK": "GBR", "Germany": "DEU", "India": "IND",
    "China": "CHN", "Russia": "RUS", "France": "FRA",
    "Canada": "CAN", "Australia": "AUS", "Brazil": "BRA",
}


def sev_badge(severity: str) -> str:
    """Return HTML badge span with icon for a severity string."""
    cls  = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium",
            "LOW": "low", "CLEAN": "clean"}.get(severity, "unknown")
    icon = SEV_ICON.get(severity, "⚪")
    return f'<span class="badge badge-{cls}">{icon} {severity}</span>'


def geo_flag(country: str) -> str:
    """Return flag emoji for a country name, or 🌐 if unknown."""
    return _FLAGS.get(country, "🌐")
