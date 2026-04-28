# =============================================================
# ⚠  DO NOT RUN IN PRODUCTION — pushes fake data to S3.
# =============================================================
# FILE: scripts/simulate_events.py
# VERSION: 1.0.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: Push synthetic OCSF events into S3 so the scanner
#          has real data to ingest and the dashboard populates.
#          Generates varied providers, departments, severities.
# USAGE:
#   python scripts/simulate_events.py [--count 50] [--profile rvdts]
# AUDIT LOG:
#   v1.0.0  2026-04-20  Initial
# =============================================================

import argparse
import json
import os
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Simulation catalog — domains must match unauthorized.csv
# ---------------------------------------------------------------------------

_PROVIDERS = [
    {"name": "OpenAI",              "domain": "api.openai.com",                  "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Anthropic Direct",    "domain": "api.anthropic.com",               "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Google Gemini",       "domain": "generativelanguage.googleapis.com","severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "xAI Grok",            "domain": "api.x.ai",                        "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Groq",                "domain": "api.groq.com",                    "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Mistral AI",          "domain": "api.mistral.ai",                  "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Cohere",              "domain": "api.cohere.com",                  "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "Perplexity",          "domain": "api.perplexity.ai",               "severity": "HIGH",     "category": "Major LLM APIs"},
    {"name": "HuggingFace",         "domain": "huggingface.co",                  "severity": "HIGH",     "category": "Open Source Model Hubs"},
    {"name": "Replicate",           "domain": "api.replicate.com",               "severity": "HIGH",     "category": "Open Source Model Hubs"},
    {"name": "AWS Bedrock Direct",  "domain": "bedrock-runtime.us-east-1.amazonaws.com", "severity": "CRITICAL", "category": "Cloud AI Platforms"},
    {"name": "Azure OpenAI",        "domain": "giggso.openai.azure.com",         "severity": "HIGH",     "category": "Cloud AI Platforms"},
    {"name": "Together AI",         "domain": "api.together.xyz",                "severity": "HIGH",     "category": "Cloud AI Platforms"},
    {"name": "Fireworks AI",        "domain": "api.fireworks.ai",                "severity": "HIGH",     "category": "Cloud AI Platforms"},
    {"name": "Pinecone",            "domain": "api.pinecone.io",                 "severity": "MEDIUM",   "category": "AI Tools and Vector DBs"},
    {"name": "Weights and Biases",  "domain": "api.wandb.ai",                    "severity": "MEDIUM",   "category": "AI Tools and Vector DBs"},
    {"name": "LangChain Hub",       "domain": "smith.langchain.com",             "severity": "MEDIUM",   "category": "AI Tools and Vector DBs"},
    {"name": "Vercel AI",           "domain": "sdk.vercel.ai",                   "severity": "HIGH",     "category": "AI Deployment Platforms"},
    {"name": "Railway",             "domain": "myapp.railway.app",               "severity": "HIGH",     "category": "AI Deployment Platforms"},
    {"name": "Fly.io",              "domain": "mybot.fly.dev",                   "severity": "HIGH",     "category": "AI Deployment Platforms"},
]

_EMPLOYEES = [
    {"owner": "Ravi Venugopal",    "department": "Engineering",  "ip": "192.168.1.42",  "hostname": "ravi-macbook"},
    {"owner": "Alice Chen",        "department": "Engineering",  "ip": "192.168.1.55",  "hostname": "alice-mbp"},
    {"owner": "Bob Patel",         "department": "Data Science", "ip": "192.168.1.63",  "hostname": "bob-linux"},
    {"owner": "Carol Kim",         "department": "Product",      "ip": "192.168.1.71",  "hostname": "carol-macbook"},
    {"owner": "David Osei",        "department": "Engineering",  "ip": "192.168.1.80",  "hostname": "david-mbp"},
    {"owner": "Eva Santos",        "department": "Marketing",    "ip": "192.168.1.91",  "hostname": "eva-macbook"},
    {"owner": "Frank Liu",         "department": "Data Science", "ip": "192.168.1.102", "hostname": "frank-ubuntu"},
    {"owner": "Grace Nwosu",       "department": "Engineering",  "ip": "192.168.1.115", "hostname": "grace-mbp"},
]

_PROCESSES = ["python3", "node", "cursor", "vscode", "jupyter", "pycharm", "npm", "deno"]


def _random_time(hours_back: int = 24) -> str:
    """Random timestamp within the last N hours."""
    delta = random.randint(0, hours_back * 3600)
    ts = datetime.now(timezone.utc) - timedelta(seconds=delta)
    return ts.isoformat()


def _make_event(provider: dict, employee: dict) -> dict:
    """Build one Packetbeat-format event dict."""
    return {
        "_hint":      "packetbeat",
        "timestamp":  _random_time(hours_back=6),
        "src_ip":     employee["ip"],
        "src_hostname": employee["hostname"],
        "dst_domain": provider["domain"],
        "dst_ip":     f"104.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
        "dst_port":   443,
        "protocol":   "TCP",
        "process_name": random.choice(_PROCESSES),
        "bytes_out":  random.randint(256, 32768),
        "owner":      employee["owner"],
        "department": employee["department"],
    }


def _build_jsonl(count: int) -> str:
    """Generate `count` events as JSONL string."""
    lines = []
    for _ in range(count):
        provider  = random.choice(_PROVIDERS)
        employee  = random.choice(_EMPLOYEES)
        event     = _make_event(provider, employee)
        lines.append(json.dumps(event))
    return "\n".join(lines)


def main() -> None:
    """Entry point — parse args, push JSONL to S3."""
    parser = argparse.ArgumentParser(description="Push simulated OCSF events to S3")
    parser.add_argument("--count",   type=int, default=50,      help="Number of events (default 50)")
    parser.add_argument("--bucket",  type=str, default="",      help="S3 bucket (default: $MARAUDER_SCAN_BUCKET)")
    parser.add_argument("--profile", type=str, default="",      help="AWS profile (default: env creds)")
    parser.add_argument("--region",  type=str, default="us-east-1")
    args = parser.parse_args()

    bucket = args.bucket or os.environ.get("MARAUDER_SCAN_BUCKET", "")
    if not bucket:
        print("ERROR: --bucket or MARAUDER_SCAN_BUCKET env var required", file=sys.stderr)
        sys.exit(1)

    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 not installed — pip install boto3", file=sys.stderr)
        sys.exit(1)

    session = boto3.Session(profile_name=args.profile or None, region_name=args.region)
    s3      = session.client("s3")

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key         = f"ocsf/{date_prefix}/packetbeat_sim_{uuid.uuid4().hex[:8]}.jsonl"
    body        = _build_jsonl(args.count).encode()

    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/x-ndjson")
    except Exception as e:
        print(f"ERROR: S3 put failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Pushed {args.count} events → s3://{bucket}/{key}")
    print("Scanner picks up within ~60 seconds. Refresh the dashboard.")


# =============================================================
# DISABLED — simulate_events.py must NOT be run in production.
# This script pushes fake data to S3 and pollutes the dashboard.
# Kept for reference only. To re-enable, uncomment the line below.
# =============================================================
# if __name__ == "__main__":
#     main()
