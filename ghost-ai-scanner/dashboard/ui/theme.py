# =============================================================
# FILE: dashboard/ui/theme.py
# VERSION: 1.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Single source of truth for PatronAI color tokens and
#          Plotly chart theming. Light theme. Every other module
#          should import from here rather than hardcoding hex.
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial — Mega-PR (light theme flip).
#   v1.1.0  2026-04-27  HIGH → red (#DC2626); MEDIUM → amber (#D97706);
#                       LOW → sky-blue (#0284C7). Icons added to sev map.
# =============================================================

# ── Color tokens ─────────────────────────────────────────────
# Surfaces
BG_PAGE      = "#F8F9FA"   # body background (off-white)
BG_CARD      = "#FFFFFF"   # cards / metric tiles / expanders
BG_SIDEBAR   = "#F1F3F5"   # subtle gray for visual separation
BG_HOVER     = "#F6F8FA"   # table-row + button hover
BG_INPUT     = "#FFFFFF"

# Text
TEXT_PRIMARY = "#1F2328"   # body copy, table cells
TEXT_VALUE   = "#0D1117"   # KPI numbers, headers — near-black
TEXT_MUTED   = "#57606A"   # captions, axis labels, help text
TEXT_LINK    = "#0969DA"   # GH light-blue link / accent

# Borders
BORDER_SOFT  = "#E1E4E8"
BORDER_HARD  = "#D0D7DE"

# Severity (updated 2026-04-27):
#   CRITICAL → deep-red   HIGH → red       MEDIUM → amber
#   LOW      → sky-blue   CLEAN → green    UNKNOWN → slate-purple
SEV: dict = {
    "CRITICAL": ("#991B1B", "rgba(153,27,27,.12)",  "rgba(153,27,27,.50)"),
    "HIGH":     ("#DC2626", "rgba(220,38,38,.10)",  "rgba(220,38,38,.45)"),
    "MEDIUM":   ("#D97706", "rgba(217,119,6,.15)",  "rgba(217,119,6,.50)"),
    "LOW":      ("#0284C7", "rgba(2,132,199,.12)",  "rgba(2,132,199,.40)"),
    "UNKNOWN":  ("#6B7280", "rgba(107,114,128,.12)","rgba(107,114,128,.30)"),
    "CLEAN":    ("#16A34A", "rgba(22,163,74,.12)",  "rgba(22,163,74,.35)"),
}

# Icon per severity — used in badges and metric labels
SEV_ICON: dict = {
    "CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡",
    "LOW": "🔵", "CLEAN": "✅", "UNKNOWN": "⚪",
}

# Plotly palettes (matches Risk + Severity stories)
PLOTLY_PALETTE = ["#0969DA", "#9A6700", "#1A7F37",
                  "#B91C1C", "#5E33B0", "#7D4E00"]


def plotly_layout() -> dict:
    """Base layout dict for every Plotly chart in the app.
    Use as: fig.update_layout(**plotly_layout(), height=...).
    Centralised so theme changes propagate without touching tabs."""
    return dict(
        template="plotly_white",
        paper_bgcolor=BG_CARD,
        plot_bgcolor=BG_CARD,
        font=dict(family="JetBrains Mono, monospace",
                  color=TEXT_MUTED, size=11),
        margin=dict(l=0, r=0, t=30, b=0),
        colorway=PLOTLY_PALETTE,
    )


def sev_colors(sev: str) -> tuple:
    """Return (fg, bg, border) hex/rgba tuple for a severity."""
    return SEV.get(sev, SEV["LOW"])
