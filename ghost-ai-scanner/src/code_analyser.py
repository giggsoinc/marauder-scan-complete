# =============================================================
# FILE: src/code_analyser.py
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 3.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Qwen 3 1.7B local inference via llama.cpp subprocess.
#          Called ONLY for AMBIGUOUS triage results from code_engine.py.
#          NOT called on every event — specialist on referral model.
#          Grammar-constrained JSON output — always valid JSON back.
#          30s timeout — never blocks scanner pipeline.
#          Model runs on EC2. Never on edge device.
#          Regex fallback fires when classifier is unreachable so layer 3
#          still produces a useful classification.
# DEPENDS: llama-cli binary in Dockerfile, Qwen 3 1.7B GGUF model
# AUDIT LOG:
#   v1.0.0  2026-04-18  Initial (Gemma 4 E4B).
#   v2.0.0  2026-04-25  Group 6.7 — regex_fallback() for model-absent / timeout paths.
#   v3.0.0  2026-04-25  Classifier swap to Qwen 3 1.7B Q4_K_M (Apache 2.0,
#                       native function-calling, ~3× smaller image footprint
#                       than Gemma 4 E4B). Same JSON contract — callers unchanged.
# =============================================================

import os
import json
import logging
import subprocess
from datetime import datetime, timezone

from code_fallback import regex_fallback

log = logging.getLogger("marauder-scan.code_analyser")

LLAMA_CLI   = os.environ.get("LLAMA_CLI_PATH",       "/usr/local/bin/llama-cli")
MODEL_PATH  = os.environ.get("CODE_ANALYSER_MODEL",  "/models/qwen3-1.7b-q4_k_m.gguf")
GRAMMAR     = os.environ.get("LLAMA_GRAMMAR_PATH",   "/etc/llama/json.gbnf")
MAX_TOKENS  = int(os.environ.get("CODE_ANALYSER_MAX_TOKENS", "250"))
TIMEOUT_SEC = int(os.environ.get("CODE_ANALYSER_TIMEOUT",    "30"))
THREADS     = int(os.environ.get("CODE_ANALYSER_THREADS",    "2"))
MODEL_NAME  = os.environ.get("CODE_ANALYSER_NAME",   "qwen3-1.7b")

# Full framework list for classification context
FRAMEWORK_CONTEXT = """
Known AI frameworks and tools to detect:
- LLM frameworks: LangChain, LangGraph, LlamaIndex, Haystack, Mastra, FastAgency
- Multi-agent: AutoGen, AG2, Microsoft Agent Framework, Semantic Kernel, CrewAI,
  OpenAI Agents SDK, Google ADK, Pydantic AI, SmolaAgents, MetaGPT
- MCP: MCPServer, stdio_server, mcp.run(), use_mcp_tool, @function_tool,
  modelcontextprotocol, mcp.Client
- Local inference: Ollama, llama-cpp-python, GPT4All, LM Studio SDK
- Hardcoded endpoints: api.openai.com, api.anthropic.com and similar
- Hardcoded keys: sk-proj-, sk-ant-, hf_ prefixes
"""

PROMPT_TEMPLATE = f"""You are a security analyst for PatronAI, a corporate AI governance platform.
Analyse the following code snippet for unauthorised AI usage.

{FRAMEWORK_CONTEXT}

Respond ONLY with a JSON object. No explanation. No markdown. No preamble.
Use this exact schema:
{{
  "ai_frameworks": ["list of detected framework names, empty if none"],
  "mcp_usage": false,
  "mcp_server_host": "",
  "agent_patterns": ["describe agent patterns found, empty if none"],
  "hardcoded_keys": false,
  "hardcoded_endpoints": ["list of hardcoded AI endpoints found"],
  "local_inference": false,
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "reasoning": "one concise sentence explaining the finding"
}}

Code snippet to analyse:
{{code}}

JSON response:"""


def analyse(code: str) -> dict:
    """
    Run the configured classifier (default: Qwen 3 1.7B) via llama-cli subprocess.
    Grammar-constrained JSON output. Never raises — falls back to regex on failure.
    """
    if not os.path.exists(MODEL_PATH):
        log.warning(f"Classifier model not at {MODEL_PATH} — using regex fallback")
        return regex_fallback(code, reason="model_not_found")

    if not os.path.exists(LLAMA_CLI):
        log.warning(f"llama-cli not at {LLAMA_CLI} — using regex fallback")
        return regex_fallback(code, reason="llama_cli_not_found")

    prompt = PROMPT_TEMPLATE.replace("{code}", code[:2000])

    cmd = [
        LLAMA_CLI,
        "--model",             MODEL_PATH,
        "--grammar-file",      GRAMMAR,
        "--temp",              "0.1",       # low temperature for classification
        "--n-predict",         str(MAX_TOKENS),
        "--threads",           str(THREADS),  # leave RAM for scanner
        "--no-display-prompt",
        "--log-disable",
        "--prompt",            prompt,
    ]

    try:
        t_start = datetime.now(timezone.utc)
        result  = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
        elapsed = (datetime.now(timezone.utc) - t_start).total_seconds()
        output  = result.stdout.strip()

        if not output:
            log.warning(f"{MODEL_NAME} returned empty output — using regex fallback")
            return regex_fallback(code, reason="empty_response")

        parsed = json.loads(output)
        parsed["_analysis_seconds"] = round(elapsed, 1)
        parsed["_model"]            = MODEL_NAME
        parsed["_analyser"]         = "marauder-scan"

        log.info(
            f"{MODEL_NAME} analysis [{elapsed:.1f}s]: risk={parsed.get('risk_level')} "
            f"frameworks={parsed.get('ai_frameworks')} "
            f"mcp={parsed.get('mcp_usage')}"
        )
        return parsed

    except subprocess.TimeoutExpired:
        log.warning(f"{MODEL_NAME} timed out after {TIMEOUT_SEC}s — using regex fallback")
        return regex_fallback(code, reason="timeout")
    except json.JSONDecodeError as e:
        log.error(f"{MODEL_NAME} JSON parse failed: {e}")
        return regex_fallback(code, reason="json_parse_failed")
    except Exception as e:
        log.error(f"Code analyser error: {e}")
        return regex_fallback(code, reason=str(e))


def is_available() -> bool:
    """Check if llama-cli and model are present. Used by alerter.py."""
    return os.path.exists(LLAMA_CLI) and os.path.exists(MODEL_PATH)


