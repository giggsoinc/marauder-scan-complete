# PatronAI — Core Package

This directory contains the PatronAI scanner, dashboard, agent delivery system,
and supporting infrastructure.

**For full documentation, quickstart, and deployment instructions see the
[root README](../README.md).**

---

## Directory Structure

```
ghost-ai-scanner/
├── src/               Python source — scanner, matcher, normaliser, alerter
│   ├── normalizer/    Event flattener + provider-name normalisation
│   ├── matcher/       Network-side rule engine
│   ├── alerter/       SNS + webhook fan-out
│   ├── ingestor/      S3-walk → pipeline → findings store
│   ├── store/         S3 persistence (BlobIndexStore + per-domain stores)
│   ├── jobs/          Background workers — hourly_rollup, docs_refresh
│   ├── query/         Rollup reader + per-user/tenant scoping
│   ├── chat/          LLM agent (engine, tools, prompts, llm transport, docs RAG)
│   └── notify/        Email — single SES call site (welcome, OTP, alert)
├── dashboard/         Streamlit UI (ghost_dashboard.py entry point)
│   └── ui/chat/       Streamlit chat panel — pure UI, calls src/chat
├── agent/             Hook agent templates (bash + PowerShell fragments)
├── config/            Provider deny/allow lists and rules (CSV + YAML)
├── scripts/           Operator scripts (setup, start, prefetch_model, deploy_to_ec2, MCP server)
├── tests/             397 unit + integration tests
├── grafana/           Pre-built dashboard provisioning
├── nginx/             Reverse proxy config
└── docs/              Technical deep-dives and inline HTML guides
```

For the full per-file index see the [Code Map section in the root
README](../README.md#code-map).

## Quick Commands

```bash
# Run unit tests (~40 seconds, no Docker needed)
pytest tests/unit/ -q

# Start the full stack
docker compose up -d

# Start the dashboard only
streamlit run dashboard/ghost_dashboard.py

# Manually trigger / backfill the chat-data hourly rollups
docker exec patronai python -m src.jobs.hourly_rollup --catch-up
docker exec patronai python -m src.jobs.hourly_rollup \
    --backfill --start 2026-04-23T00 --end 2026-04-30T00
```

See [`../README.md`](../README.md) for full environment variable reference,
deployment guide, and architecture diagram.
See [`docs/chat-rollups.md`](docs/chat-rollups.md) for the chat data backend
(per-user + per-tenant hourly rollups) and how to operate it.

---

© 2026 Giggso Inc · [Apache 2.0](../LICENSE)
