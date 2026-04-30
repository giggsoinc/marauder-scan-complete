# =============================================================
# FILE: src/normalizer/provider_names.py
# VERSION: 1.0.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Map raw provider strings emitted by agent_explode (e.g.
#          "claude.ai", "github.copilot", "pip:openai") to human
#          AI-tool names ("Anthropic Claude", "GitHub Copilot",
#          "OpenAI SDK"). Single source of truth for tool identity.
#          Loaded by hourly_rollup.py — no Streamlit, no dashboard imports.
# DEPENDS: stdlib only
# =============================================================

from __future__ import annotations

import csv
import logging
import os
from functools import lru_cache
from typing import Optional

log = logging.getLogger("marauder-scan.normalizer.provider_names")

# Built-in identity dictionary. Keys are LOWERCASE raw-provider strings
# as emitted by agent_explode._provider_for(). Extend over time.
_KNOWN_AI_TOOLS: dict[str, str] = {
    # ── Browser (key = bare domain) ──────────────────────────
    "chatgpt.com":           "OpenAI ChatGPT",
    "chat.openai.com":       "OpenAI ChatGPT",
    "claude.ai":             "Anthropic Claude",
    "gemini.google.com":     "Google Gemini",
    "aistudio.google.com":   "Google AI Studio",
    "perplexity.ai":         "Perplexity",
    "huggingface.co":        "HuggingFace",
    "cursor.com":            "Cursor",
    "manus.im":              "Manus",
    "flowiseai.com":         "Flowise",
    "v0.dev":                "Vercel v0",
    "bolt.new":              "Bolt",
    "lovable.dev":           "Lovable",
    "notebooklm.google.com": "NotebookLM",
    "grok.x.ai":             "xAI Grok",
    "mistral.ai":            "Mistral",
    "cohere.com":            "Cohere",
    "replit.com":            "Replit",
    # ── IDE plugins (key = plugin_id, lowercased) ────────────
    "github.copilot":         "GitHub Copilot",
    "github.copilot-chat":    "GitHub Copilot",
    "continue.continue":      "Continue",
    "codeium.codeium":        "Codeium",
    "supermaven.supermaven":  "Supermaven",
    "tabnine.tabnine-vscode": "Tabnine",
    "anthropic.claude-vscode": "Anthropic Claude (IDE)",
    # ── Packages (key = "manager:name") ──────────────────────
    "pip:openai":              "OpenAI SDK",
    "pip:anthropic":           "Anthropic SDK",
    "pip:langchain":           "LangChain",
    "pip:langchain-core":      "LangChain",
    "pip:langgraph":           "LangGraph",
    "pip:llama-index":         "LlamaIndex",
    "pip:llama_index":         "LlamaIndex",
    "pip:transformers":        "HuggingFace Transformers",
    "pip:sentence-transformers": "HuggingFace Transformers",
    "pip:crewai":              "CrewAI",
    "pip:autogen":             "AutoGen",
    "pip:pyautogen":           "AutoGen",
    "pip:chromadb":            "ChromaDB",
    "pip:faiss-cpu":           "FAISS",
    "pip:faiss-gpu":           "FAISS",
    "pip:lancedb":             "LanceDB",
    "pip:pinecone":            "Pinecone",
    "pip:pinecone-client":     "Pinecone",
    "pip:weaviate-client":     "Weaviate",
    "npm:openai":              "OpenAI SDK",
    "npm:@anthropic-ai/sdk":   "Anthropic SDK",
    "npm:langchain":           "LangChain",
    "npm:@langchain/core":     "LangChain",
    "npm:llamaindex":          "LlamaIndex",
    # ── Processes (key = process name, lowercased) ───────────
    "ollama":   "Ollama",
    "lmstudio": "LM Studio",
    "lm studio": "LM Studio",
    "flowise":  "Flowise",
    "n8n":      "n8n",
    "langflow": "Langflow",
}


@lru_cache(maxsize=1)
def _unauthorized_csv_map() -> dict[str, str]:
    """Load config/unauthorized.csv (domain → display name) once.
    Returns {} on any error so a missing/broken file never crashes the
    rollup. Cache cleared on process restart — daily refresh is enough."""
    candidates = [
        os.environ.get("UNAUTHORIZED_CSV", ""),
        os.path.join(os.path.dirname(__file__), "..", "..", "config", "unauthorized.csv"),
        "/app/config/unauthorized.csv",
        "config/unauthorized.csv",
    ]
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            mapping: dict[str, str] = {}
            with open(path, newline="", encoding="utf-8") as f:
                # Skip comment lines that start with '#'
                lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
                reader = csv.DictReader(lines)
                for row in reader:
                    name   = (row.get("name") or "").strip()
                    domain = (row.get("domain") or "").strip().lower()
                    if name and domain and not domain.startswith("*"):
                        mapping[domain] = name
            log.info("provider_names: loaded %d domain mappings from %s",
                     len(mapping), path)
            return mapping
        except Exception as exc:
            log.warning("provider_names: failed to load %s: %s", path, exc)
            continue
    log.info("provider_names: no unauthorized.csv found; using built-in map only")
    return {}


def normalize_provider(category: str, raw_provider: str) -> str:
    """Return a human-readable AI-tool name. Falls back to raw_provider
    when no mapping exists so unknown providers still surface (but with
    their raw key — so we can spot them in audit logs and add to the dict).

    Args:
        category: finding category from schema (browser, package, ide_plugin, ...)
        raw_provider: provider field as emitted by agent_explode._provider_for
    """
    if not raw_provider:
        return ""
    key = raw_provider.strip().lower()

    # Browser: try unauthorized.csv first (tenant-curated), then built-in.
    if category == "browser":
        csv_map = _unauthorized_csv_map()
        if key in csv_map:
            return csv_map[key]
        if key in _KNOWN_AI_TOOLS:
            return _KNOWN_AI_TOOLS[key]
        # Try parent domain (e.g. cdn-lfs.huggingface.co → huggingface.co)
        parts = key.split(".")
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            if parent in csv_map:
                return csv_map[parent]
            if parent in _KNOWN_AI_TOOLS:
                return _KNOWN_AI_TOOLS[parent]
        return raw_provider  # surface as-is

    # Other categories: built-in dict only.
    if key in _KNOWN_AI_TOOLS:
        return _KNOWN_AI_TOOLS[key]
    return raw_provider


def is_known(category: str, raw_provider: str) -> bool:
    """Used by rollup audit-log to flag unmapped providers worth adding."""
    if not raw_provider:
        return True
    key = raw_provider.strip().lower()
    if category == "browser":
        return key in _unauthorized_csv_map() or key in _KNOWN_AI_TOOLS
    return key in _KNOWN_AI_TOOLS


def reset_caches() -> None:
    """Test/CLI hook — drop the unauthorized.csv cache."""
    _unauthorized_csv_map.cache_clear()
