# =============================================================
# FILE: dashboard/ui/chat/llm/base.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Abstract base class for all PatronAI LLM transports.
#          Each transport (openai_compat, anthropic) subclasses
#          LLMClient and implements the two methods below.
#          engine.py is transport-agnostic — it only calls these.
# DEPENDS: stdlib (abc)
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Provider-agnostic LLM interface used by engine.py.

    Normalised response from complete():
      {
        "content":    str | None,   # final text — set when no tool calls
        "tool_calls": list | None,  # [{id, name, arguments: dict}] | None
        "raw_msg":    dict,         # provider-native message to append to history
      }
    """

    @abstractmethod
    def complete(self, messages: list, tools: list) -> dict:
        """Send messages + tool schema; return normalised response dict."""

    @abstractmethod
    def tool_result_msg(self, tool_call_id: str,
                        tool_name: str, content: str) -> dict:
        """Build the provider-native tool-result message to append after
        executing a tool. Providers differ here:
          - OpenAI-compat: {"role":"tool", "tool_call_id":..., "content":...}
          - Anthropic:     user message with tool_result content block
        """
