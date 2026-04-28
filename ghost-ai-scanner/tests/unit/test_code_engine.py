# =============================================================
# FILE: tests/unit/test_code_engine.py
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Unit tests for Marauder Scan code pattern matcher.
#          Tests department scope, authorized-first, all outcomes.
#          No AWS calls.
# =============================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from matcher.code_engine import triage, CodeOutcome

AUTHORIZED = [
    {"name": "LangChain",   "type": "framework", "pattern": "langchain",   "dept_scope": "Engineering", "notes": ""},
    {"name": "LlamaIndex",  "type": "framework", "pattern": "llama_index", "dept_scope": "",             "notes": "Company-wide"},
]

UNAUTHORIZED = [
    {"name": "MCPServer",   "type": "mcp",       "pattern": "MCPServer",   "severity": "HIGH"},
    {"name": "AutoGen",     "type": "framework", "pattern": "autogen",     "severity": "HIGH"},
    {"name": "CrewAI",      "type": "framework", "pattern": "crewai",      "severity": "HIGH"},
    {"name": "Hardcoded",   "type": "api",       "pattern": "api.openai.com", "severity": "CRITICAL"},
]


# ── Authorized suppression ────────────────────────────────────

def test_langchain_suppressed_in_engineering():
    snippet = "from langchain import LLMChain\nchain = LLMChain(llm=llm)"
    v = triage(snippet, "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == CodeOutcome.SUPPRESS


def test_langchain_not_suppressed_in_finance():
    """LangChain authorized for Engineering ONLY — Finance must alert."""
    snippet = "from langchain import LLMChain"
    v = triage(snippet, "Finance", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] != CodeOutcome.SUPPRESS


def test_company_wide_auth_suppressed_any_dept():
    """LlamaIndex has no dept scope — suppressed everywhere."""
    snippet = "from llama_index import VectorStoreIndex"
    for dept in ["Engineering", "Finance", "Legal", "HR"]:
        v = triage(snippet, dept, AUTHORIZED, UNAUTHORIZED)
        assert v["outcome"] == CodeOutcome.SUPPRESS, f"Failed for dept: {dept}"


def test_authorized_checked_before_unauthorized():
    """Authorized must be checked first — no false alerts on approved tools."""
    # LangChain is in both authorized (Engineering) and would match patterns
    snippet  = "from langchain import LLMChain"
    v_eng    = triage(snippet, "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v_eng["outcome"] == CodeOutcome.SUPPRESS


# ── Unauthorized code alerts ──────────────────────────────────

def test_mcp_server_alert():
    snippet = "server = MCPServer()\nserver.register_tool(my_tool)"
    v = triage(snippet, "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"]       == CodeOutcome.CODE_ALERT
    assert v["severity"]      == "HIGH"
    assert v["matched_name"]  == "MCPServer"


def test_autogen_alert():
    snippet = "import autogen\nassistant = autogen.AssistantAgent('assistant')"
    v = triage(snippet, "DevOps", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"]  == CodeOutcome.CODE_ALERT
    assert v["severity"] == "HIGH"


def test_crewai_alert():
    snippet = "from crewai import Crew, Agent\ncrew = Crew(agents=[])"
    v = triage(snippet, "Marketing", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == CodeOutcome.CODE_ALERT


def test_hardcoded_endpoint_critical():
    snippet = 'BASE_URL = "https://api.openai.com/v1/chat/completions"'
    v = triage(snippet, "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"]  == CodeOutcome.CODE_ALERT
    assert v["severity"] == "CRITICAL"


# ── Ambiguous ─────────────────────────────────────────────────

def test_bare_openai_import_ambiguous():
    """'openai' alone is ambiguous — could be authorized via Parameter Store."""
    snippet = "import openai\nclient = openai.OpenAI()"
    v = triage(snippet, "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == CodeOutcome.AMBIGUOUS


# ── Unknown ───────────────────────────────────────────────────

def test_clean_code_unknown():
    snippet = "def calculate_roi(revenue, cost):\n    return (revenue - cost) / cost"
    v = triage(snippet, "Finance", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"]  == CodeOutcome.UNKNOWN
    assert v["severity"] == "LOW"


def test_empty_snippet_unknown():
    v = triage("", "Engineering", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == CodeOutcome.UNKNOWN


# ── Multiple signals ──────────────────────────────────────────

def test_first_unauthorized_match_wins():
    """When multiple unauthorized patterns present — first match returned."""
    snippet = "import autogen\nfrom crewai import Crew"
    v = triage(snippet, "Research", AUTHORIZED, UNAUTHORIZED)
    assert v["outcome"] == CodeOutcome.CODE_ALERT
