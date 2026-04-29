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
├── dashboard/         Streamlit UI (ghost_dashboard.py entry point)
├── agent/             Hook agent templates (bash + PowerShell fragments)
├── config/            Provider deny/allow lists and rules (CSV + YAML)
├── scripts/           Deployment and maintenance scripts
├── tests/             353 unit + integration tests
├── grafana/           Pre-built dashboard provisioning
├── nginx/             Reverse proxy config
└── docs/              Technical deep-dives and inline HTML guides
```

## Quick Commands

```bash
# Run unit tests (~40 seconds, no Docker needed)
pytest tests/unit/ -q

# Start the full stack
docker compose up -d

# Start the dashboard only
streamlit run dashboard/ghost_dashboard.py
```

See [`../README.md`](../README.md) for full environment variable reference,
deployment guide, and architecture diagram.

---

© 2026 Giggso Inc · [Apache 2.0](../LICENSE)
