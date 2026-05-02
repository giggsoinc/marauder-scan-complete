# =============================================================
# FILE: src/chat/llm/openai_compat.py
# VERSION: 1.4.0
# UPDATED: 2026-05-02
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
#   v1.2.0  2026-04-29  Remove Qwen3-specific chat_template_kwargs;
#                       model switched to LFM2.5-1.2B-Thinking.
#   v1.3.0  2026-04-30  Read timeout 60→180 (LFM2.5-Thinking emits long
#                       reasoning before tool calls); add max_tokens cap.
#   v1.4.0  2026-05-02  Strip reasoning blocks from user-visible content.
#                       LFM2.5-Thinking sometimes emits raw reasoning
#                       ("Okay, let's tackle this user query…") into
#                       message.content instead of message.reasoning_content.
#                       The chat panel was showing this verbatim.
#                       Now: `<think>…</think>` blocks removed; explicit
#                       reasoning preambles stripped; if everything ends
#                       up empty after stripping, fall back to the raw
#                       text so the user gets *something*.
# =============================================================

import json
import logging
import os
import re

import requests

from .base import LLMClient

log = logging.getLogger("patronai.chat.llm.openai")

_TIMEOUT    = int(os.environ.get("LLM_READ_TIMEOUT_S", "180"))
_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))

# Patterns thinking-class models emit when they leak reasoning into
# message.content. We strip these before showing the answer.
_THINK_BLOCK_RE = re.compile(
    r"<think>.*?</think>|<thinking>.*?</thinking>|<reasoning>.*?</reasoning>",
    re.IGNORECASE | re.DOTALL,
)
# A leading paragraph that's clearly the model thinking aloud. Keep
# this list narrow — false positives here would corrupt real answers.
_REASONING_LEAD_RE = re.compile(
    r"^\s*(?:Okay|Alright|Hmm|Wait|Let me|Looking at|First[, ]|"
    r"The user (?:wants|is asking|said))[^\n]*\n+",
    re.IGNORECASE,
)


def _strip_reasoning(text: str) -> str:
    """Remove visible reasoning leakage from a model's content field.

    Order:
      1. Drop explicit <think>/<thinking>/<reasoning> blocks.
      2. Strip a single leading reasoning paragraph (Okay/Hmm/Wait/…).
      3. If stripping leaves nothing, return the original text — better
         to show messy reasoning than a blank panel.
    """
    if not text:
        return text
    out = _THINK_BLOCK_RE.sub("", text)
    out = _REASONING_LEAD_RE.sub("", out)
    out = out.strip()
    return out if out else text


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
        payload: dict = {"messages": messages, "temperature": 0,
                         "max_tokens": _MAX_TOKENS}
        if self._model:
            payload["model"] = self._model
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"

        resp = requests.post(self._url, json=payload, headers=self._headers,
                             timeout=(10, _TIMEOUT))
        if not resp.ok:
            log.error("LLM %d: %s", resp.status_code, resp.text[:400])
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
        content = _strip_reasoning(content)
        return {"content": content, "tool_calls": None, "raw_msg": msg}

    def tool_result_msg(self, tool_call_id: str,
                        tool_name: str, content: str) -> dict:
        """OpenAI-format tool result message."""
        return {"role": "tool", "tool_call_id": tool_call_id,
                "name": tool_name, "content": content}
