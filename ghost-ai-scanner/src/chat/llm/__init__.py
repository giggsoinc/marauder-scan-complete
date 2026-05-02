# =============================================================
# FILE: src/chat/llm/__init__.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: LLM client factory. Reads config from env vars first,
#          then AWS Parameter Store (SSM) as fallback — so local
#          dev uses .env and EC2 production uses Parameter Store
#          with zero code changes.
#
#          Default: openai_compat → http://localhost:8080 (llama.cpp)
#
#          To switch provider, set these (env or SSM):
#            LLM_PROVIDER  openai_compat | anthropic
#            LLM_BASE_URL  base URL for openai_compat
#            LLM_API_KEY   bearer token (empty = no auth for local)
#            LLM_MODEL     model name (empty = server default)
#
#          SSM parameter paths: /patronai/llm/{var_name_lowercase}
#            e.g. /patronai/llm/api_key, /patronai/llm/provider
# DEPENDS: boto3, .openai_compat, .anthropic
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

import logging
import os

import boto3
from botocore.exceptions import ClientError

from .base          import LLMClient
from .openai_compat import OpenAICompatClient
from .anthropic     import AnthropicClient

log = logging.getLogger("patronai.chat.llm")

_SSM_PREFIX = "/patronai/llm/"
_DEFAULTS = {
    "provider": "openai_compat",
    "base_url": "http://localhost:8080",    # llama-server default port
    "api_key":  "",
    "model":    "",                         # llama-server uses the loaded model; set for cloud APIs
}


def _cfg(key: str) -> str:
    """Read config: env var first, then SSM Parameter Store, then default.
    Env var name: LLM_{KEY.upper()} (e.g. LLM_API_KEY).
    SSM path: /patronai/llm/{key} (e.g. /patronai/llm/api_key).
    """
    env_name = f"LLM_{key.upper()}"
    # 1. Environment variable (.env or shell)
    val = os.environ.get(env_name, "")
    if val:
        return val
    # 2. AWS SSM Parameter Store (production)
    try:
        ssm  = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        resp = ssm.get_parameter(Name=_SSM_PREFIX + key, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except ClientError:
        pass  # parameter not set — use default
    except Exception as exc:
        log.debug("SSM lookup failed for %s: %s", key, exc)
    # 3. Built-in default
    return _DEFAULTS.get(key, "")


def get_client() -> LLMClient:
    """Return a configured LLMClient for the active provider.

    Called once per chat turn by engine.py (cheap — no network I/O here).
    Raises ValueError for unknown provider names.
    """
    provider = _cfg("provider").lower()

    if provider == "anthropic":
        api_key = _cfg("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "Anthropic provider selected but no API key found. "
                "Set LLM_API_KEY or ANTHROPIC_API_KEY (env or SSM).")
        return AnthropicClient(api_key=api_key, model=_cfg("model"))

    if provider == "openai_compat":
        return OpenAICompatClient(
            base_url=_cfg("base_url"),
            api_key=_cfg("api_key"),
            model=_cfg("model"))

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Valid values: openai_compat | anthropic")
