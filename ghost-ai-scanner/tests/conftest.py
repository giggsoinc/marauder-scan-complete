# =============================================================
# FILE: tests/conftest.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Shared pytest fixtures using LocalStack for AWS mocks.
#          All tests use these fixtures — no real AWS calls.
#          LocalStack must be running before test suite executes.
#          Start with: docker-compose -f docker-compose.dev.yml up localstack -d
# =============================================================

import os
import json
import pytest
import boto3
from datetime import date

# ── LocalStack endpoint ───────────────────────────────────────
LOCALSTACK_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
TEST_BUCKET    = os.environ.get("MARAUDER_SCAN_BUCKET", "marauder-scan-test")
TEST_REGION    = os.environ.get("AWS_REGION", "us-east-1")
TEST_COMPANY   = "test"

# Force all boto3 calls to LocalStack
os.environ.setdefault("AWS_ACCESS_KEY_ID",     "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION",    TEST_REGION)
os.environ.setdefault("AWS_ENDPOINT_URL",      LOCALSTACK_URL)
os.environ.setdefault("MARAUDER_SCAN_BUCKET",  TEST_BUCKET)

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(scope="session")
def s3_client():
    """S3 client pointing at LocalStack."""
    return boto3.client(
        "s3",
        region_name=TEST_REGION,
        endpoint_url=LOCALSTACK_URL,
    )


@pytest.fixture(scope="session")
def sns_client():
    """SNS client pointing at LocalStack."""
    return boto3.client(
        "sns",
        region_name=TEST_REGION,
        endpoint_url=LOCALSTACK_URL,
    )


@pytest.fixture(scope="session")
def test_bucket(s3_client):
    """Create test bucket in LocalStack once per session."""
    try:
        s3_client.create_bucket(Bucket=TEST_BUCKET)
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        pass
    return TEST_BUCKET


@pytest.fixture(scope="session")
def seeded_bucket(test_bucket, s3_client):
    """Seed test bucket with config files."""
    # authorized.csv
    s3_client.put_object(
        Bucket=test_bucket,
        Key="config/authorized.csv",
        Body=b"name,domain_pattern,notes\nTrinity,trinity.internal.com,Approved proxy\n",
    )
    # unauthorized.csv — minimal test version
    s3_client.put_object(
        Bucket=test_bucket,
        Key="config/unauthorized.csv",
        Body=(
            b"name,category,domain,port,severity,notes\n"
            b"OpenAI,LLM API,*.openai.com,,HIGH,\n"
            b"HuggingFace,Model Hub,*.huggingface.co,,HIGH,\n"
            b"Ollama,Local Inference,,11434,MEDIUM,Local model server\n"
        ),
    )
    # authorized_code.csv
    s3_client.put_object(
        Bucket=test_bucket,
        Key="config/authorized_code.csv",
        Body=b"name,type,pattern,dept_scope,notes\nLangChain,framework,langchain,Engineering,Approved\n",
    )
    # unauthorized_code.csv — minimal test version
    s3_client.put_object(
        Bucket=test_bucket,
        Key="config/unauthorized_code.csv",
        Body=(
            b"name,type,pattern,severity,notes\n"
            b"MCPServer,mcp,MCPServer,HIGH,\n"
            b"AutoGen,framework,autogen,HIGH,\n"
            b"CrewAI,framework,crewai,HIGH,\n"
            b"Hardcoded OpenAI,api,api.openai.com,CRITICAL,\n"
        ),
    )
    # settings.json
    settings = {
        "company":  {"slug": TEST_COMPANY},
        "cloud":    {"provider": "aws", "region": TEST_REGION},
        "scanner":  {"scan_interval_secs": 60},
        "alerts":   {"sns_topic_arn": "", "dedup_window_minutes": 5},
        "storage":  {"ocsf_bucket": test_bucket},
        "_meta":    {"last_written_by": "test"},
    }
    s3_client.put_object(
        Bucket=test_bucket,
        Key="config/settings.json",
        Body=json.dumps(settings).encode(),
    )
    return test_bucket


@pytest.fixture
def store(seeded_bucket):
    """BlobIndexStore pointed at LocalStack test bucket."""
    from blob_index_store import BlobIndexStore
    return BlobIndexStore(seeded_bucket, TEST_REGION)


@pytest.fixture
def sample_packetbeat_event():
    return {
        "@timestamp": "2026-04-18T09:14:32Z",
        "source":      {"ip": "10.0.4.112", "mac": "00:1A:2B:3C:4D:5E", "bytes": 2847392},
        "destination": {"ip": "104.18.7.192", "domain": "api.openai.com", "port": 443},
        "network":     {"transport": "tcp"},
        "process":     {"name": "python3"},
    }


@pytest.fixture
def sample_flow_log_line():
    return "2 123456789 eni-abc123 10.0.4.112 34.105.12.44 54321 443 6 10 2847392 1713345272 1713345332 ACCEPT OK"


@pytest.fixture
def sample_code_signal():
    return {
        "event_type":  "CODE_SIGNAL",
        "source":      "agent_fs_watcher",
        "device_id":   "macbook-dev-01",
        "company":     TEST_COMPANY,
        "file_path":   "/home/dev/project/agent.py",
        "snippet":     "from autogen import AssistantAgent, UserProxyAgent\nassistant = AssistantAgent('assistant')\n",
        "timestamp":   "2026-04-18T09:14:32Z",
    }


@pytest.fixture
def sample_git_diff():
    return {
        "event_type":   "GIT_DIFF_SIGNAL",
        "source":       "marauder_scan_git_hook",
        "device_id":    "macbook-dev-01",
        "company":      TEST_COMPANY,
        "repo":         "ai-project",
        "branch":       "feature/add-agent",
        "diff_snippet": "+from crewai import Crew, Agent\n+crew = Crew(agents=[Agent(role='researcher')])\n",
        "timestamp":    "2026-04-18T09:20:00Z",
    }
