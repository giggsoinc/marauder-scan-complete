# =============================================================
# FILE: src/code_fallback.py
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Regex-only classifier used when Gemma 4 E4B is
#          unreachable (model missing, llama-cli missing, timeout,
#          or JSON parse fail). Mirrors Gemma response schema so
#          downstream code paths are unchanged.
# DEPENDS: stdlib (re)
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 6.7 — Gemma resilience.
# =============================================================

import re

_FRAMEWORK_RE = re.compile(
    r"\b(langchain|langgraph|llama[-_]index|haystack|autogen|crewai|"
    r"semantic[-_]kernel|pydantic[-_]ai|smolagents|metagpt|mastra|fastagency)\b",
    re.IGNORECASE,
)
_MCP_RE = re.compile(
    r"\b(mcp\.run|stdio_server|use_mcp_tool|MCPServer|modelcontextprotocol|mcp\.Client)\b"
)
_KEY_RE = re.compile(
    r"\b(sk-proj-[A-Za-z0-9_-]{8,}|sk-ant-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{8,})\b"
)
_ENDPOINT_RE = re.compile(
    r"https?://(api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com)\S*",
    re.IGNORECASE,
)
_LOCAL_INF_RE = re.compile(
    r"\b(ollama|llama[-_]cpp[-_]python|gpt4all|lm[-_]studio)\b", re.IGNORECASE,
)


def regex_fallback(code: str, reason: str = "fallback") -> dict:
    """Best-effort regex-only classifier; runs when Gemma is unreachable."""
    snippet = (code or "")[:8000]
    frameworks = sorted({m.group(0).lower() for m in _FRAMEWORK_RE.finditer(snippet)})
    endpoints  = sorted({m.group(0)         for m in _ENDPOINT_RE.finditer(snippet)})
    mcp_hit    = bool(_MCP_RE.search(snippet))
    key_hit    = bool(_KEY_RE.search(snippet))
    local_hit  = bool(_LOCAL_INF_RE.search(snippet))
    if key_hit:
        risk = "CRITICAL"
    elif frameworks or mcp_hit or endpoints:
        risk = "HIGH"
    elif local_hit:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return {
        "ai_frameworks":       frameworks,
        "mcp_usage":           mcp_hit,
        "mcp_server_host":     "",
        "agent_patterns":      ["regex-detected agent framework"] if frameworks else [],
        "hardcoded_keys":      key_hit,
        "hardcoded_endpoints": endpoints,
        "local_inference":     local_hit,
        "risk_level":          risk,
        "reasoning":           f"Regex fallback ({reason}) — Gemma unreachable.",
        "_fallback":           reason,
        "_model":              "regex-fallback",
        "_analyser":           "marauder-scan",
    }
