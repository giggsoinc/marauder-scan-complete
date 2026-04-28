# =============================================================
# FILE: src/store/agent_renderer.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Renders shell/PowerShell installer templates.
#          Replaces {{PLACEHOLDER}} tokens with real values.
#          Caller provides a context dict — all keys upper-cased.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — agent delivery system
# =============================================================

import logging
import re
from pathlib import Path

log = logging.getLogger("marauder-scan.agent_renderer")

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def render(template_path: str, context: dict) -> str:
    """
    Read template file and substitute {{KEY}} tokens from context.
    Keys in context are matched case-insensitively.
    Missing keys raise KeyError to surface misconfiguration early.
    """
    try:
        template_text = Path(template_path).read_text(encoding="utf-8")
    except Exception as e:
        log.error("Cannot read template [%s]: %s", template_path, e)
        raise

    upper_ctx = {k.upper(): v for k, v in context.items()}
    missing   = []

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in upper_ctx:
            missing.append(key)
            return match.group(0)
        return str(upper_ctx[key])

    rendered = _PLACEHOLDER.sub(_replace, template_text)

    if missing:
        raise KeyError(f"Template placeholders not resolved: {missing}")

    return rendered
