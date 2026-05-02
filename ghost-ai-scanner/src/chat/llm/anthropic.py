# =============================================================
# FILE: src/chat/llm/anthropic.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Anthropic Claude transport via Messages API (requests only,
#          no anthropic SDK). Converts OpenAI-format tool schema and
#          message history to Anthropic format internally — engine.py
#          remains format-agnostic.
#          Config: ANTHROPIC_API_KEY env var / Parameter Store.
#          Model:  LLM_MODEL env var (e.g. claude-3-5-haiku-20241022).
# DEPENDS: requests
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import json
import logging
from typing import Optional

import requests

from .base import LLMClient

log = logging.getLogger("patronai.chat.llm.anthropic")

_API_URL = "https://api.anthropic.com/v1/messages"
_VERSION = "2023-06-01"
_TIMEOUT = 60


def _to_anthropic_tools(oai_tools: list) -> list:
    """Convert OpenAI tool schema list → Anthropic tools list."""
    out = []
    for t in oai_tools:
        fn = t.get("function", {})
        out.append({"name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters",
                                          {"type": "object", "properties": {}})})
    return out


def _to_anthropic_messages(messages: list) -> tuple[list, Optional[str]]:
    """Split OpenAI-format messages into (anthropic_messages, system_prompt).
    Converts tool/tool_calls messages to Anthropic content blocks."""
    system: Optional[str] = None
    out: list = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system = m.get("content", "")
            continue
        if role == "tool":
            # Merge into previous user message or start new one
            block = {"type": "tool_result",
                     "tool_use_id": m.get("tool_call_id", ""),
                     "content": m.get("content", "")}
            if out and out[-1]["role"] == "user":
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        # assistant with tool_calls
        if role == "assistant" and m.get("tool_calls"):
            blocks = []
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use",
                                "id":   tc.get("id", ""),
                                "name": tc["function"]["name"],
                                "input": json.loads(
                                    tc["function"].get("arguments", "{}"))})
            out.append({"role": "assistant", "content": blocks})
            continue
        # plain text message
        content = m.get("content") or ""
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        else:
            out.append({"role": role, "content": content})
    return out, system


class AnthropicClient(LLMClient):
    """Transport for Anthropic Claude via the Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._key   = api_key
        self._model = model or "claude-3-5-haiku-20241022"

    def complete(self, messages: list, tools: list) -> dict:
        """Call Anthropic Messages API; return normalised response."""
        anth_msgs, system = _to_anthropic_messages(messages)
        payload: dict = {"model": self._model, "max_tokens": 1024,
                         "messages": anth_msgs}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = _to_anthropic_tools(tools)

        headers = {"x-api-key": self._key,
                   "anthropic-version": _VERSION,
                   "content-type": "application/json"}
        resp = requests.post(_API_URL, json=payload,
                             headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # Extract tool_use blocks if present
        content_blocks = data.get("content", [])
        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
        if tool_uses:
            tcs = [{"id": b["id"], "name": b["name"],
                    "arguments": b.get("input", {})}
                   for b in tool_uses]
            # raw_msg in Anthropic format for appending to history
            raw = {"role": "assistant", "content": content_blocks}
            return {"content": None, "tool_calls": tcs, "raw_msg": raw}

        text = " ".join(b.get("text", "") for b in content_blocks
                        if b.get("type") == "text").strip()
        return {"content": text or "(no response)", "tool_calls": None,
                "raw_msg": {"role": "assistant", "content": content_blocks}}

    def tool_result_msg(self, tool_call_id: str,
                        tool_name: str, content: str) -> dict:
        """Anthropic tool result — user message with tool_result block."""
        return {"role": "user",
                "content": [{"type": "tool_result",
                              "tool_use_id": tool_call_id,
                              "content": content}]}
