# Quickstart — Local Development

This guide gets PatronAI running on your laptop in under 10 minutes,
**without AWS or a paid account.**

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker + Docker Compose | ≥ 25 | `docker --version` |
| Python | 3.12 or 3.13 | for unit tests only |
| Git | any | |

No AWS account, no API keys, no cloud required for local dev.

---

## Step 1 — Clone

```bash
git clone https://github.com/giggso/patronai.git
cd patronai/ghost-ai-scanner
```

---

## Step 2 — Configure environment

```bash
cp .env.example .env
```

Minimal `.env` for local mode (no S3, no SMTP):

```dotenv
# ── Required ──────────────────────────────────────
COMPANY_NAME=Acme Corp
SECRET_KEY=any-random-string-here

# ── Leave blank for local-only mode ───────────────
MARAUDER_SCAN_BUCKET=
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# ── AI Chat (optional) ────────────────────────────
# If you have Ollama running: gemma3:4b or similar
LLAMA_SERVER_URL=http://localhost:8080
```

> **Local mode**: with `MARAUDER_SCAN_BUCKET` blank the dashboard runs in
> demo/stub mode — you can browse the UI but findings are synthetic.
> S3 is only needed for real agent data.

---

## Step 3 — Start the stack

```bash
docker compose up -d
```

This starts:
- **patronai** — scanner + Streamlit dashboard (port 8501)
- **grafana** — metrics dashboard (port 3000, `admin/admin`)
- **nginx** — reverse proxy (port 80)

First build downloads ~500 MB of Python packages and compiles llama.cpp
(~5 min on a modern laptop). Subsequent starts are seconds.

---

## Step 4 — Open the dashboard

```
http://localhost:8501
```

Default credentials (local mode):

| Email | Password | Role |
|-------|----------|------|
| admin@local | `patronai` | admin |

> In production these are stored in S3 (`s3://your-bucket/users/users.json`).
> See the full deployment guide in `README.md`.

---

## Step 5 — Run the unit tests

```bash
# From ghost-ai-scanner/
pip install -r requirements.txt
pytest tests/unit/ -q
```

Expected: **353 tests pass**, ~40 seconds, no network required.

---

## Step 6 (optional) — Enable AI chat

If you have [Ollama](https://ollama.ai) installed:

```bash
ollama pull gemma3:4b
# Then set in .env:
# LLAMA_SERVER_URL=http://localhost:11434/v1
```

Or start llama.cpp server with the bundled Qwen 3 model (after baking):

```bash
docker exec -it patronai \
  llama-server --model /models/qwen3-1.7b-q4_k_m.gguf --port 8080 --ctx-size 4096
```

Open any dashboard view → scroll to bottom → **🤖 Ask AI** expander.

---

## Useful Commands

```bash
# View logs
docker compose logs -f patronai

# Rebuild after code changes
docker compose build patronai && docker compose up -d patronai

# Run a single test file
pytest tests/unit/test_scanner.py -v

# Stop everything
docker compose down

# Stop + remove volumes (wipe local state)
docker compose down -v
```

---

## Project Layout

```
ghost-ai-scanner/
├── src/               Python source — scanner, matcher, normaliser, alerter
├── dashboard/         Streamlit UI
│   └── ui/            Views, widgets, chat engine
├── agent/             Hook agent templates (bash + PowerShell)
├── config/            Provider deny/allow lists, rules (CSV + YAML)
├── scripts/           Deploy + maintenance scripts
├── tests/             353 unit + integration tests
└── docs/              Technical deep-dives
```

---

## Next Steps

- **Deploy to EC2** — see `README.md` → Deployment section
- **Add your first agent** — Settings → Deploy Agents
- **Connect Grafana alerts** — Settings → Alerting
- **Contribute a new provider** — see `CONTRIBUTING.md`
