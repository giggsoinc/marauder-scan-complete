# =============================================================
# FRAGMENT: scan_redactor.py.frag
# PROJECT: PatronAI — Phase 1A
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Shared redactor used by every Phase 1A scanner before a
#          finding leaves the laptop. Strips API keys / JWTs / generic
#          high-entropy tokens; replaces user-home prefixes with `~`.
#          Privacy gate: a finding that contains a string matching the
#          secret regex AFTER redaction is dropped entirely (never
#          shipped half-redacted) — the caller logs the drop.
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A. Used by scan_mcp_configs,
#                       scan_agents_workflows, scan_tools_code,
#                       scan_vector_dbs.
# =============================================================

# Named provider patterns. Deliberately broad on the value side —
# false-positive redactions are safe; false-negatives leak.
# The generic "catch-all base64 blob" used to live here but was removed
# because it matched legitimate SHA-256 hex hashes (config_sha256
# fields). Add new named patterns here as new providers appear.
_SECRET_RE = re.compile(
    r"(?i)("
    r"sk-ant-[A-Za-z0-9_\-]{20,}|"                     # Anthropic explicit (specific first)
    r"sk-[A-Za-z0-9_\-]{20,}|"                         # OpenAI / generic sk- family
    r"hf_[A-Za-z0-9]{20,}|"                            # HuggingFace
    r"AKIA[0-9A-Z]{16}|"                               # AWS access key
    r"AIza[0-9A-Za-z_\-]{35}|"                         # Google API
    r"ghp_[A-Za-z0-9]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|"  # GitHub PAT family
    r"xox[baprs]-[A-Za-z0-9\-]{10,}|"                  # Slack
    r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"  # JWT
    r")"
)

_HOME_RE = re.compile(re.escape(str(Path.home())))


def _redact_text(text: str) -> str:
    """Run secret-strip + home-path-strip on a string. Safe on None/empty."""
    if not text:
        return text or ""
    return _HOME_RE.sub("~", _SECRET_RE.sub("***REDACTED***", text))


def _safe_path(path) -> str:
    """Render a Path or str with the home dir replaced by `~`."""
    return _HOME_RE.sub("~", str(path)) if path else ""


def _redact_value(value):
    """Recursive — redact strings inside dicts/lists; pass other types through."""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


def _has_unredacted_secret(blob) -> bool:
    """Return True if `blob` (string or container) STILL contains a secret
    after redaction — caller drops the finding when this is True."""
    if isinstance(blob, str):
        return bool(_SECRET_RE.search(blob))
    if isinstance(blob, dict):
        return any(_has_unredacted_secret(v) for v in blob.values())
    if isinstance(blob, (list, tuple)):
        return any(_has_unredacted_secret(v) for v in blob)
    return False


def _safe_finding(finding: dict) -> dict:
    """Apply redaction to every string field of a finding dict.
    Caller is responsible for dropping the result if `_has_unredacted_secret`
    returns True after this pass."""
    return {k: _redact_value(v) for k, v in finding.items()}
