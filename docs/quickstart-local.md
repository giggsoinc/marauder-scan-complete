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
| S3 bucket | existing | or [LocalStack](https://localstack.cloud) for fully offline dev |

---

## First-boot checklist

Read these before starting — they prevent the most common surprises:

| | What to know |
|---|---|
| 🔑 **Email-only login** | PatronAI has **no password field**. Add your email to `ALLOWED_EMAILS` in `.env` — that is your login credential. There is no `admin@local / patronai` default. |
| ⬇️ **LLM download on first start** | `docker compose up` triggers a background download of LFM2.5-1.2B-Thinking (~750 MB Q4_K_M) into the `patronai-models` Docker volume via `llama-server --hf-repo`. The dashboard opens immediately; the persistent **🤖 Ask PatronAI** side panel activates once the download finishes (~3-5 min). |
| 📧 **SNS confirmation email** | If you ran `prereqs.sh`, AWS sent a subscription confirmation to `ADMIN_EMAILS`. You **must click that link** — if you skip it, alert emails are silently dropped with no error logged. |
| 🔒 **Grafana password is required** | `GF_SECURITY_ADMIN_PASSWORD` must be set in `.env` (compose refuses to start without it). `setup.sh` auto-generates a 32-char random one if you press Enter at the prompt; otherwise paste your own. **No `admin/admin` default ships any more.** |

---

## Step 1 — Clone

```bash
git clone https://github.com/giggsoinc/patronai.git
cd patronai/ghost-ai-scanner
```

---

## Step 2 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the **5 REQUIRED lines** at the top. Everything else has a safe default:

```dotenv
# ── REQUIRED — fill in these 5 ────────────────────
PATRONAI_BUCKET=my-patronai-bucket   # must already exist in S3
COMPANY_NAME=Acme Corp
COMPANY_SLUG=acme
ADMIN_EMAILS=you@yourcompany.com
ALLOWED_EMAILS=you@yourcompany.com

# ── AWS credentials (leave blank on EC2 with instance profile) ─
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
```

> **S3 required.** PatronAI reads and writes all findings, agent events, and
> config to S3. Create a bucket first: `aws s3 mb s3://my-patronai-bucket`
> Use [LocalStack](https://localstack.cloud) for a fully offline bucket.

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

Enter the email you set in `ALLOWED_EMAILS`. No password field — press Enter or click **Sign in**.

> **First-time login creates your user record** in S3 at
> `s3://{PATRONAI_BUCKET}/users/users.json`. Admin access is determined by
> whether your email appears in `ADMIN_EMAILS`.

---

## Step 5 — Run the unit tests

```bash
# From ghost-ai-scanner/
pip install -r requirements.txt
pytest tests/unit/ -q
```

Expected: **353 tests pass**, ~40 seconds, no network required.

---

## Step 6 — AI chat

AI chat is on by default — no action needed. PatronAI downloads
[LiquidAI LFM2.5-1.2B-Thinking](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF)
(~750 MB Q4_K_M) into the `patronai-models` Docker volume on first start.
Once ready, every dashboard view shows a persistent **🤖 Ask PatronAI**
side panel. Answers cite real S3 paths from per-tenant hourly rollups,
and how-to questions are answered from BM25-indexed HTML+MD docs.

**To use Ollama instead** (if you have it running locally):

```dotenv
# In .env:
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=lfm2:1b
```

```bash
ollama pull lfm2:1b           # or any tool-calling capable model
docker compose restart patronai
```

**Refreshing docs after edits.** When you change any file under `docs/`
or `ghost-ai-scanner/docs/`, ask the chat *"refresh docs"* (it calls
`refresh_docs()`) or wait up to 5 min for the auto-refresh daemon —
the BM25 index rebuilds when any indexed file's mtime advances.

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
