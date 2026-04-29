# =============================================================
# FILE: dashboard/ui/chat/llm/openai_compat.py
# VERSION: 1.1.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: OpenAI-compatible LLM transport. Works with ANY
#          endpoint that speaks /v1/chat/completions:
#            • llama.cpp server   (local, default)
#            • Ollama             (local, port 11434)
#            • OpenAI             (https://api.openai.com)
#            • Groq               (https://api.groq.com/openai)
#            • Together AI        (https://api.together.xyz)
#            • LM Studio / vLLM  (any local OpenAI-compat server)
#          Config via env / Parameter Store (see llm/__init__.py).
# DEPENDS: requests
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
#   v1.1.0  2026-04-29  Disable Qwen3 thinking mode for local servers;
#                       fallback to reasoning_content if content empty.
# =============================================================

import json
import logging

import requests

from .base import LLMClient

log = logging.getLogger("patronai.chat.llm.openai")

_TIMEOUT = 60


class OpenAICompatClient(LLMClient):
    """Transport for any OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(self, base_url: str, api_key: str = "",
                 model: str = "") -> None:
        """Initialise with endpoint config.

        Args:
            base_url: Full base URL, no trailing slash.
            api_key:  Bearer token. Empty string = no auth (local models).
            model:    Model name string. Empty = let the server decide.
        """
        self._url   = base_url.rstrip("/") + "/v1/chat/completions"
        self._model = model
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def complete(self, messages: list, tools: list) -> dict:
        """POST to /v1/chat/completions; return normalised response.

        Raises requests.exceptions.ConnectionError if server is down
        (caught by engine.py for fallback logic).
        """
        payload: dict = {"messages": messages, "temperature": 0}
        if self._model:
            payload["model"] = self._model
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"
        # Disable Qwen3 thinking mode for local llama-server (no-op on cloud APIs).
        if not self._headers.get("Authorization"):
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        resp = requests.post(self._url, json=payload,
                             headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]

        raw_tcs = msg.get("tool_calls") or []
        if raw_tcs:
            tcs = [{"id":        tc["id"],
                    "name":      tc["function"]["name"],
                    "arguments": json.loads(
                        tc["function"].get("arguments", "{}"))}
                   for tc in raw_tcs]
            return {"content": None, "tool_calls": tcs, "raw_msg": msg}

        content = msg.get("content") or msg.get("reasoning_content") or "(no response)"
        return {"content": content, "tool_calls": None, "raw_msg": msg}

    def tool_result_msg(self, tool_call_id: str,
                        tool_name: str, content: str) -> dict:
        """OpenAI-format tool result message."""
        return {"role": "tool", "tool_call_id": tool_call_id,
                "name": tool_name, "content": content}
