# =============================================================
# FILE: dashboard/ui/chat/engine.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: PatronAI chat engine — transport-agnostic tool-call loop.
#          Injects system prompt, calls LLMClient.complete(), executes
#          tool functions from tools.py, loops until text or max rounds.
#          The only LLM-aware logic is the loop; format details live in
#          the transport (llm/openai_compat.py or llm/anthropic.py).
# DEPENDS: chat/tools.py, chat/prompts.py, chat/llm/, chat/tools_schema.py
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import json
import logging

import requests

from .tools        import (get_summary_stats, get_top_risky_users,
                            get_user_risk_profile, query_findings,
                            get_fleet_status, get_shadow_ai_census,
                            get_recent_activity, compare_periods)
from .help         import get_help
from .tools_schema import TOOLS_SCHEMA
from .prompts      import build_system_prompt
from .llm          import get_client

log = logging.getLogger("patronai.chat.engine")

_MAX_ROUNDS = 5  # tool-call loop guard

# ── Tool dispatch table ───────────────────────────────────────

_TOOL_FNS = {
    "get_summary_stats":     get_summary_stats,
    "get_top_risky_users":   get_top_risky_users,
    "get_user_risk_profile": get_user_risk_profile,
    "query_findings":        query_findings,
    "get_fleet_status":      get_fleet_status,
    "get_shadow_ai_census":  get_shadow_ai_census,
    "get_recent_activity":   get_recent_activity,
    "compare_periods":       compare_periods,
    "get_help":              get_help,
}


def _run_tool(name: str, arguments: dict, events: list) -> str:
    """Execute one tool and return its result as a JSON string.

    The first positional argument to every tool function is `events`.
    Extra kwargs from the LLM are passed as keyword arguments.
    Returns a JSON error string on any failure so the LLM can report it.
    """
    fn = _TOOL_FNS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        result = fn(events, **arguments) if arguments else fn(events)
        return json.dumps(result, default=str)
    except Exception as exc:
        log.warning("tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ── Public API ────────────────────────────────────────────────

def call_llm(messages: list, events: list, view: str,
             email: str, company: str) -> str:
    """Run a full chat turn: inject system prompt, execute tool loop,
    return the final assistant text string.

    Args:
        messages: Conversation history — [{"role":..., "content":...}, ...]
                  Already includes the latest user message.
        events:   Role-scoped event list (never leaves this process).
        view:     "exec" | "manager" | "support"
        email:    Logged-in user email.
        company:  Company name for system prompt.

    Raises:
        RuntimeError: If no LLM provider is reachable or config is invalid.
    """
    sys_msg  = {"role": "system",
                "content": build_system_prompt(events, view, email, company)}
    # Keep last 20 messages to stay within the 8192-token context window.
    all_msgs = [sys_msg] + messages[-20:]

    try:
        client = get_client()
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        for _round in range(_MAX_ROUNDS):
            result = client.complete(all_msgs, TOOLS_SCHEMA)

            if result["tool_calls"]:
                # Append the assistant's tool_call message
                all_msgs.append(result["raw_msg"])
                # Execute each requested tool
                for tc in result["tool_calls"]:
                    output = _run_tool(tc["name"], tc["arguments"], events)
                    log.debug("tool %s → %d chars", tc["name"], len(output))
                    all_msgs.append(
                        client.tool_result_msg(tc["id"], tc["name"], output))
                continue  # loop — LLM will now summarise tool results

            # Plain text response — done
            return result["content"] or "(empty response)"

        return "I reached the tool-call limit — please rephrase your question."

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "LLM server is unreachable. "
            "Start llama-server, Ollama, or check LLM_BASE_URL.") from exc
    except Exception as exc:
        raise RuntimeError(f"LLM error: {exc}") from exc
