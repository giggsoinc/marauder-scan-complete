# PatronAI

<p align="left">
  <img src="assets/branding/patronai-logo.png" alt="PatronAI" width="320"/>
</p>

Enterprise AI governance and security platform. Detects unauthorised AI tool
usage across corporate networks and source code.

PatronAI ingests VPC Flow Logs, Packetbeat and Zeek telemetry, normalises to
OCSF, and matches against a deny-all provider list of 70+ AI services. A
**Marauder Scan** code layer detects AI frameworks (LangChain, CrewAI, AutoGen
and 40+ others), MCP servers and hardcoded API keys at git commit time via
GitLeaks custom rules. Qwen 3 1.7B via llama.cpp classifies ambiguous code
signals on EC2 — never on edge devices. Apache 2.0; ~1 GB at Q4 quant.

Single Docker container. Multi-cloud. Deploys on Fargate, Cloud Run or ACI.
Grafana dashboards pre-built and provisioned on first boot.

---

## What It Does

Scans OCSF-normalised network logs from S3 every N minutes.
Compares all traffic against a deny-all list of 70+ AI providers.
Fires alerts to SNS and Trinity on any unauthorised match.
Serves pre-built Grafana dashboards (Exec governance view, Manager IT-admin view).
Writes pre-aggregated daily summaries so dashboards stay fast at scale.
Calls LogAnalyzer on demand for deep RCA — never continuously.

---

## Architecture

```
Edge layer (Packetbeat + Zeek + Marauder Scan hook agent)
        ↓
OCSF normalisation (3 input format parsers)
        ↓
S3 bucket (single source of truth)
        ↓
Service 1: PatronAI scanner + Streamlit UI (port 8501 behind nginx :80)
Service 2: Grafana dashboards (subpath /grafana behind nginx :80)
        ↓
SNS → Trinity → AIRTaaS
```

**Hook Agent Delivery** — Admins generate personalised installers from the
Streamlit Deploy Agents tab. Each installer is OTP-locked and uploaded to
`config/HOOK_AGENTS/` in the tenant S3 bucket. Recipients receive a 48-hour
presigned link via SES email. A macOS DMG and Windows EXE are built
automatically on EC2 at generation time (genisoimage / makensis) — no Mac
or Windows machine needed.

The agent installs a git pre-commit hook, an endpoint scan (every 30 min:
pip/npm/brew packages, running processes, browser history matched against
the unauthorised provider list), and a heartbeat (every 5 min liveness ping).
All three report back to S3 via presigned PUT URLs baked into the installer.

Per-user authorised domains are set at generation time and stored in
`config/HOOK_AGENTS/{token}/authorized.csv`. Admins can edit the whitelist
from the Deploy Agents table at any time — the agent fetches the updated
list on its next scan without reinstalling.

One flag switches clouds:

```bash
CLOUD_PROVIDER=aws   # default
CLOUD_PROVIDER=gcp
CLOUD_PROVIDER=azure
```

---

## Quick Start — AWS

Run all commands from `marauder-scan-complete/` (the repo root, one level above this directory).

### Step 1 — Deploy EC2 and transfer code (Mac)

```bash
bash deploy_to_ec2.sh
```

What it does: creates EC2 instance, attaches IAM instance profile, rsyncs the codebase, optionally installs Docker. Follow the prompts — no flags needed.

---

### Step 2 — Provision AWS infrastructure (on EC2)

SSH into the EC2 instance when `deploy_to_ec2.sh` finishes, then:

```bash
cd marauder-scan
bash prereqs.sh
```

What it does: creates S3 bucket, SNS alert topic, IAM role and scoped policy, configures VPC Flow Log delivery to S3, writes `.env`. Confirm the SNS subscription email when it arrives.

---

### Step 3 — Start the scanner

```bash
docker-compose up -d
```

Three containers start: `scanner` (PatronAI + Streamlit), `grafana`, `nginx`.

---

### Step 4 — Populate ENI metadata cache

Run once after first boot so the VPC Flow Log filter can classify ENIs:

```bash
docker exec marauder-scan python3 scripts/refresh_eni_cache.py
```

Cache is written to `s3://{bucket}/cache/eni_metadata.json` and auto-refreshes every 6 hours after that.

---

### Step 5 — Set up agent delivery (run once after containers are up)

```bash
bash scripts/setup_hook_agents.sh
```

Creates `config/HOOK_AGENTS/catalog.json` in the S3 bucket, validates S3 write
permissions and SES identity. Safe to re-run.

---

### Step 6 — Open the platform

| Surface | URL | Who |
|---|---|---|
| PatronAI UI (all views) | `http://<ec2-ip>/` | All roles |
| Grafana dashboards | `http://<ec2-ip>/grafana/` | Admin / Support |

nginx routes `/` → Streamlit (port 8501) and `/grafana/` → Grafana (port 3000).
Direct ports 8501 and 3000 are not exposed; use nginx only.

**Roles**

| Env var | Role | Views available |
|---|---|---|
| `ADMIN_EMAILS` | Admin | All views + Settings + Deploy Agents |
| `SUPPORT_EMAILS` | Support | Support · Manager · Exec |
| _(all others)_ | User | Exec view + Provider Lists (read-only) |

---

### Teardown (full removal)

To remove all AWS resources created by PatronAI and start clean:

```bash
# Run from marauder-scan-complete/
bash teardown.sh
```

Type `TEARDOWN marauder-scan-<company>` when prompted. Removes EC2, S3, SNS, IAM role, VPC Flow Log. Writes a timestamped removal report to `ghost-ai-scanner/reports/`.

---

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| CLOUD_PROVIDER | No | aws | Cloud adapter to load (aws / gcp / azure) |
| MARAUDER_SCAN_BUCKET | Yes | — | S3 bucket (single source of truth) |
| ALERT_SNS_ARN | No | — | SNS topic ARN for alerts |
| TRINITY_WEBHOOK_URL | No | — | Trinity incident webhook |
| SCAN_INTERVAL_SECS | No | 300 | Scan frequency in seconds |
| LOOKBACK_MINUTES | No | 60 | First boot lookback window |
| COMPANY_NAME | No | — | Company name shown in UI header |
| CROWDSTRIKE_ENABLED | No | false | Show endpoint process data in dashboards |
| DEDUP_WINDOW_MINUTES | No | 60 | Alert deduplication window per source per provider |
| AWS_REGION | No | us-east-1 | AWS region |
| ADMIN_EMAILS | Yes | — | Comma-separated admin email addresses |
| SUPPORT_EMAILS | No | — | Comma-separated support team email addresses |
| PUBLIC_HOST | No | — | EC2 public IP or DNS (no protocol, no trailing slash) — used to build absolute Grafana links |
| GRAFANA_URL | No | — | Full Grafana base URL (takes precedence over PUBLIC_HOST) |
| ALERT_RECIPIENTS | No | — | Comma-separated email addresses for SES alert emails |
| PATRONAI_FROM_EMAIL | No | noreply@patronai.ai | SES verified sender address |
| STRICT_MIN_RULES | No | 50 | Self-check threshold. Below this, matcher emits CRITICAL `degraded_ruleset` finding and the UI shows a red banner. |
| URL_REFRESH_INTERVAL_SECS | No | 86400 | How often the EC2 scanner re-mints presigned URL bundles for every active hook-agent token (Step 0). |
| INCLUDE_CLASSIFIER | No | 0 | Docker build arg. `1` bakes the Qwen 3 1.7B GGUF (~1 GB) into the image. Otherwise mount at `/models` or rely on `code_fallback.regex_fallback()`. |
| QWEN_GGUF_REPO | No | Qwen/Qwen3-1.7B-GGUF | HuggingFace repo for the classifier GGUF. Override to a community quantizer (e.g. `bartowski/Qwen3-1.7B-GGUF`) if the official repo is unavailable. |
| LLAMA_CPP_TAG | No | b4404 | llama.cpp release tag. Bump only after verifying Qwen 3 architecture support. |
| CODE_ANALYSER_MODEL | No | /models/qwen3-1.7b-q4_k_m.gguf | Path inside the container to the GGUF. |
| CODE_ANALYSER_NAME | No | qwen3-1.7b | Free-form model label stamped onto every classification result (`_model` field). |

`setup.sh` auto-detects EC2 public IP and writes `PUBLIC_HOST` and `GRAFANA_URL` to `.env`.
All values can also be set via the Streamlit settings UI.
Settings written to S3 `config/settings.json`. Active within one scan cycle.

---

## VPC Flow Log Filtering

VPC Flow Logs capture every ENI in the VPC — including AWS-managed infrastructure ENIs that will never produce AI signals. Without filtering, these consume S3 GET cost and scanner CPU on every cycle.

PatronAI applies a 5-type ENI denylist **before** normalisation:

| Type | Match | Reason |
|---|---|---|
| EFS mount target | `Description` starts with `"EFS mount target"` OR `RequesterId = 641247547298` | Storage protocol only — all rows NODATA |
| NAT Gateway | `InterfaceType = nat_gateway` | Aggregates all outbound traffic — masks real src |
| VPC Endpoint | `InterfaceType = vpc_endpoint` | AWS PrivateLink only — never reaches external AI providers |
| Load Balancer | `Description` starts with `"ELB "` | Inbound forwarder — real client is originating device |
| Lambda idle ENI | `Description` starts with `"AWS Lambda VPC ENI"` | Idle NODATA floods — Lambda AI calls attributed server-side |

Only ENIs where `RequesterManaged=False` **and** `OwnerId` matches the customer AWS account are normalised and passed to the matcher.

**ENI metadata cache** — `s3://{bucket}/cache/eni_metadata.json`
- Populated by `scripts/refresh_eni_cache.py` (calls `ec2:DescribeNetworkInterfaces`)
- Refreshed every 6 hours inline by the normaliser (module-level TTL check)
- Cache miss = fail open — flows from unknown ENIs are never silently dropped
- Filter counts logged as `eni_filtered_total{reason=efs|nat|vpce|elb|lambda}` every 1,000 rows

Denylist rules: `config/eni_denylist.yaml` — add new ENI types here without code changes.

---

## Provider Lists

CSV files in `config/`. Reload on every scan cycle — no restart after edits.

### Network deny (traffic-side)

**`config/unauthorized.csv`** — Giggso baseline. 70+ AI providers across 5 categories.
Pushed from the Docker image to S3 on every container start (always overwritten).
Read-only in the UI, by design.

**`config/unauthorized_custom.csv`** — Customer additions. Edited via the
**Provider Lists → Custom denylist** tab in Streamlit. Survives Docker rebuilds.
Merged with the baseline at scan time. On `(domain, port)` collision **custom wins** —
letting customers locally tighten severity or add notes.

### Code deny (Marauder Scan layer)

**`config/unauthorized_code.csv`** — Giggso baseline. AI framework / MCP / agent
patterns matched against committed code diffs. 90+ entries.

**`config/unauthorized_code_custom.csv`** — Customer additions. Same merge model
as the network list. Edited via **Provider Lists → Custom code denylist**.

### Allow list

**`config/authorized.csv`** — Customer-owned. Editable in the UI. Suppresses alerts
for approved endpoints (Trinity proxy, internal AI gateway, etc.).

### Editing flow (admin)

1. Open Streamlit → **Provider Lists** tab.
2. **Bulk import** (optional) — expand `📥 Bulk import from CSV`, drop a file. Rows
   are run through the same `rule_model` pipeline as a manual save: schemes, paths,
   quotes, zero-width chars, mixed case, trailing dots are stripped. A summary card
   shows `✓ N valid · ⚠ M skipped`. Skipped rows surface in an expander with reasons
   and a `Download issues CSV` button so admins can fix offline. Click `Load N valid
   rows into editor` — clean rows append to the editor (deduped on `(domain, port)`,
   imported wins).
3. **Manual edit** — type, paste, or delete rows directly in the table. The `🔎 Find`
   filter above the editor highlights matches without changing the editor. The `🗑
   Clear` button empties the editor (Save with empty contents to wipe S3 — recorded
   in the audit log).
4. **Save** — invalid rows surface inline with the reason. Conflicts with your allow
   list surface as a yellow banner with a *Save anyway (override)* button. Within one
   scan cycle (~5 min) the new rule fires.

### Validation (single source of truth)

`src/matcher/rule_model.py` is the contract. Same code runs at UI save and at scanner
load. Each row passes through `normalize_domain` + `valid_glob` + `is_too_broad` +
severity enum + port range. Bad rows are rejected at write so the loader never has to
defend itself.

### Strict-mode boot

If the merged deny count is below `STRICT_MIN_RULES` (env, default `50`), the system
**does not exit** — it logs CRITICAL, writes `config/load_status.json`, and emits a
`degraded_ruleset` finding so SNS/Trinity page on-call. The dashboard stays up so
admins can fix the issue from the UI. A red banner appears on Provider Lists.

### Discovered AI tools — sustainable curation (Group 2)

Manual list-curation doesn't scale — every AI tool launch becomes another row to
add. The Provider Lists tab includes a **Discovered AI tools — review queue**
section that aggregates the last 7 days of `UNKNOWN`-verdict findings, ranks by
event count, and surfaces them for one-click promotion. Admins choose:

- **Promote to deny** — appends the domain to `unauthorized_custom.csv` (audit-logged).
- **Dismiss** — persists in `config/discovered_dismissed.txt`; the row hides on next render.

The matcher's *"never silently pass"* contract turns into a discovery loop: novel AI
tools your users actually hit are surfaced for triage instead of waiting for Giggso
to add them upstream.

### RBAC + time format + per-grid search (Phase 1B)

Three rough edges removed from the daily-use experience:

- **RBAC via `s3://patronai/users/users.json`.** Three base roles
  (`exec` / `manager` / `support`) plus an orthogonal `is_admin` flag.
  Admins see everything + Settings; other roles see their own view +
  Provider Lists. The `Users` settings tab is now interactive — admins
  can add, edit, or remove users without redeploying. First dashboard
  load auto-migrates from `ALLOWED_EMAILS` / `ADMIN_EMAILS` env vars
  one-time so existing access doesn't break.
- **Human-readable timestamps everywhere.** `26-APR-26 14:30:45 IST`
  format rendered in the viewer's local browser timezone, with raw
  UTC ISO available on hover for audit copy-paste. Single helper at
  `dashboard/ui/time_fmt.py`; consumed by every grid + chart axis.
- **Global search bar on every grid.** Substring match across all
  string columns; case-insensitive; live result-count caption. Risks,
  Inventory, Logs, AI Inventory, Signals, Rules — every table now has
  one. Single helper at `dashboard/ui/filtered_table.py`.

### MCP / Agent / Tools / Vector-DB inventory + Asset Map (Phase 1A)

Four new finding categories surface on the **Manager → AI INVENTORY** tab:

- **MCP servers** — read from Claude Desktop / Cursor / Continue / Cline JSON configs. Server name + command basename + arg flags + env-var keys (no values). SHA-256 hash on the parent file detects edits and fires an `MCP_CONFIG_CHANGED` alert when something changes.
- **Agent workflows** — n8n / Flowise / langflow JSONs and YAMLs sitting on disk waiting to run.
- **Scheduled agents** — cron + macOS launchd entries that mention AI keywords.
- **Tool registrations** — `@tool` / `@function_tool` / `Tool(...)` decorators inside auto-discovered git repos. Counts only — never ships the source.
- **Vector DBs** — Chroma, FAISS, LanceDB, Qdrant, Milvus, DuckDB-vector files in home caches OR inside repos.

Each finding passes through the shared **secret redactor** before upload (API keys, JWTs, paths). Findings that still contain secrets after redaction are dropped entirely. Repos are auto-discovered by walking `$HOME` for `.git/` directories — **no hardcoded paths.** Configurable exclusions in `config/repo_discovery.yaml`.

Click any owner email cell in the AI INVENTORY tab to open the **AI ASSET MAP** for that user — Plotly Treemap (User → Repo → Category → Asset) plus a nested expander tree.

### Server-side data flow + per-finding events (Step 0.5)

The dashboard previously showed empty even when agents were healthy. Step 0.5
fixes two stacked server-side bugs:

- **Cursor switched from filename to "last-modified time."** Files the
  agent overwrites in place (heartbeats, scans → `latest.json`) now get
  re-read on every cycle instead of being seen exactly once.
- **ENDPOINT_SCAN no longer dropped silently.** Each finding inside a
  scan payload becomes its own flat event: a browser hit lands as a row
  with `dst_domain` set; an installed package lands with `process_name`;
  an IDE plugin lands with the plugin id; container images and shell
  history land with their own distinctive fields. Each event is tagged
  with a `scan_id` so all findings from the same scan can be grouped.

Clean scans (zero findings) drop entirely — the 5-minute heartbeat
already proves the agent is alive; we don't bloat storage with empty
"scan ran fine" rows. The existing alerter pipeline routes HIGH /
CRITICAL findings into SNS / Trinity / SES with the existing dedup
window, and dashboards back-fill from `ocsf/findings/YYYY/MM/DD/`
within one cycle of deploy.

### Auto-coverage for future repos (Step 0.1)

The agent installs the pre-commit hook into every existing repo at install
time, but Step 0.1 closes the *future* gap so coverage doesn't decay:

- Sets `init.templateDir = ~/.patronai/git-template/` so every `git init`
  and `git clone` automatically gets the pre-commit hook.
- Every 5 minutes (heartbeat cycle), walks `$HOME` (depth 6) and ensures
  every `.git/hooks/pre-commit` is our symlink — catches anything cloned
  before the agent was installed.

If a customer already has `init.templateDir` set (e.g. for Husky / lefthook
templating), the installer is **additive** — it copies our hook into their
existing template dir and leaves the rest untouched. Uninstall reverses both
changes cleanly.

### Endpoint data flow + identity binding (Step 0)

Hook agents now carry a unique identity bundle on every payload:
`token + email + device_uuid + mac_primary + ip_set + hostname`.
Email is baked from the recipient form at installer-generation time.
`device_uuid` is generated once on first install and persisted.
`mac_primary` is captured at install. `ip_set` refreshes each cycle.

Presigned write URLs are **refreshable**: the EC2 scanner re-mints
heartbeat / scan / authorized URLs daily and writes a per-token
`urls.json` bundle. The agent fetches the bundle on every heartbeat
and overwrites its local URL files — no more 7-day silent cliff.
No AWS credentials live on the laptop; the trust model is unchanged.

If a recipient suspects something is wrong, they run:

```bash
bash ~/.patronai/diagnose.sh    # macOS / Linux
powershell -File ~/.patronai/diagnose.ps1   # Windows
```

The script prints config, current IPs, URL-file presence, the last
20 `agent.log` entries, and runs a live PUT probe with HTTP-status
diagnosis (403 → URL expired, 0 → network blocked, 2xx → healthy).

### Endpoint scan coverage (Group 2)

The hook agent's 30-min endpoint scan is multi-surface and cross-OS:

| Surface | What's checked | OS support |
|---|---|---|
| Packages | pip / npm / brew / choco / winget against AI-package regex | macOS · Linux · Windows |
| Processes | `ps aux` / `tasklist` against AI-process regex | macOS · Linux · Windows |
| Browser history | Safari · Chrome · Firefox · Edge · Brave · Arc · Opera · Vivaldi · Chromium | macOS · Linux · Windows |
| IDE plugins | VS Code / Cursor / vscode-server extensions; every JetBrains IDE plugin dir | macOS · Linux · Windows |
| Containers | `docker ps -a` image-name + `docker logs --tail 500` (no `exec`) | All Docker hosts |
| Shell history | `~/.bash_history` · `~/.zsh_history` · fish · PowerShell `ConsoleHost_history.txt` | macOS · Linux · Windows |

Scan logic lives in `agent/install/scan_*.py.frag` fragments — one set serves both
bash and PowerShell installers. See [../WHY_FRAGMENTS_AND_WHERE.md](../WHY_FRAGMENTS_AND_WHERE.md)
for the full architecture.

### Matcher logic

1. Check `authorized.csv` first. Match → suppress silently.
2. Check `unauthorized.csv` + `unauthorized_custom.csv` (merged) domain column. Match → alert.
3. Check merged port column. Match → alert MEDIUM.
4. No match anywhere → flag UNKNOWN LOW. Never silently pass.
5. Authorized domain but no CloudTrail GetParameter → personal key detected. Alert HIGH.

---

## S3 Bucket Structure

```
s3://marauder-scan-{company}/        # bucket name preserved from v1 infra
├── config/
│   ├── authorized.csv                 customer allow list (editable)
│   ├── unauthorized.csv               Giggso baseline deny (overwritten on deploy)
│   ├── unauthorized_custom.csv        customer additions (survives rebuilds)
│   ├── unauthorized_code.csv          Giggso baseline code-deny
│   ├── unauthorized_code_custom.csv   customer code additions
│   ├── load_status.json               written by self_check_rules() — UI banner source
│   ├── settings.json
│   └── HOOK_AGENTS/                 agent delivery workspace
│       ├── catalog.json             index of all provisioned agents
│       └── {token}/
│           ├── meta.json            recipient metadata + expiry + authorized_domains[]
│           ├── authorized.csv       per-user tool whitelist (editable from UI)
│           ├── setup_agent.sh       rendered shell installer (Mac/Linux)
│           ├── setup_agent.ps1      rendered PowerShell installer (Windows)
│           ├── PatronAI-Agent-{name}.dmg   macOS HFS image (auto-built on EC2)
│           ├── PatronAI-Agent-{name}.exe   Windows EXE (auto-built on EC2 via NSIS)
│           └── status.json          install status (written by agent on success)
├── ocsf/
│   ├── YYYY/MM/DD/           incoming OCSF files (network telemetry)
│   └── agent/
│       ├── git-diffs/        GIT_DIFF_SIGNAL events from pre-commit hooks
│       └── scans/{token}/
│           └── latest.json   latest ENDPOINT_SCAN result per agent (network telemetry)
├── findings/YYYY/MM/DD/
│   ├── critical.jsonl
│   ├── high.jsonl
│   ├── medium.jsonl
│   └── unknown.jsonl
├── summary/daily/            pre-aggregated stats for dashboards
├── cursor/state.json         last processed S3 key
├── dedup/YYYY-MM-DD.json     alert deduplication records
├── identity/nac-mapping.csv  IP to MAC to user fallback
└── reports/                  generated PDFs
```

> Bucket prefix `marauder-scan-` is retained to avoid disrupting active VPC
> Flow Logs, IAM policies and the current EC2 deployment. New customers can
> opt into `patronai-{company}` via Terraform variable.

---

## Dashboards and Views

### Grafana (at `/grafana/`)

Two pre-built dashboards provisioned on first boot.

**Exec dashboard** (`/grafana/d/marauder-overview`) — AI governance for executives.
- Tab 1: AI Landscape — bubble chart, world map, MCP topology
- Tab 2: Risk Heatmap — department × severity, top offenders
- Tab 3: Data Exposure — Sankey diagram, incident timeline
- Three drill-downs: provider, department, incident

**Manager dashboard** — Infrastructure IT admin.
- Tab 1: Inventory — all assets, MAC, geo, CrowdStrike banner
- Tab 2: Risks — open alerts, source system, reviewer
- Tab 3: Log View — raw OCSF browser, S3 Select, geo + flag
- Tab 4: Alerts — pipeline health, SNS log, scan status
- Drill to raw OCSF JSON on any event

### Streamlit UI (at `/`)

Role-gated single-page app. Views vary by role:

| View | Role | Content |
|---|---|---|
| **Exec view** | All | KPI metrics, Sankey, provider exposure map |
| **Manager view** | Admin / Support | Risk table, actions (resolve/escalate/email), log export |
| **Support view** | Admin / Support | Rules health, code signals, coverage %, pipeline health |
| **Provider Lists** | All (read-only) | Authorized + unauthorized CSV viewer |
| **Settings** | Admin only | Scanning · Alerting · Identity · Provider Lists · Users · Deploy Agents |

#### Deploy Agents tab (Admin → Settings)

1. Fill: Name, Email, Platform (Mac/Linux/Windows).
2. Optionally enter **Authorised tools** — one domain per line (e.g. `canva.com`). Suppresses those domains from scan findings for this user only.
3. Click **Generate & Send** — renders OTP-locked sh + ps1, uploads all files to `config/HOOK_AGENTS/{token}/`, builds DMG and EXE on EC2, emails recipient a 48-hour presigned download link + 6-digit OTP.
4. DMG and EXE download links appear in the table within 30 seconds.
5. Status column auto-refreshes — shows `PENDING` → `INSTALLED` as agents check in.
6. To update a user's whitelist: click **Whitelist** on the table row → edit domains → Save. Agent picks up changes within 30 min, no reinstall.

---

## Hook Agent Delivery

The hook agent installs three active monitors on the developer's machine:

| Monitor | Trigger | What it detects |
|---|---|---|
| **Git pre-commit hook** | Every `git commit` | AI framework imports, MCP server refs, hardcoded API keys (sk-proj-, sk-ant-, hf_) |
| **Endpoint scan** | Every 30 min | pip/npm/brew AI packages; running processes (n8n, Ollama, Cursor, LM Studio); browser history (Safari, Chrome, Firefox/Edge) matched against unauthorised provider list |
| **Heartbeat** | Every 5 min | Device liveness — hostname, OS, agent version |

All findings go to S3 as OCSF events → scanner pipeline → Pam/Steve dashboards.

### Admin workflow

```bash
# 1. One-time setup after docker-compose up
bash scripts/setup_hook_agents.sh

# 2. Check all provisioned agents
aws s3 ls s3://$MARAUDER_SCAN_BUCKET/config/HOOK_AGENTS/ --recursive

# DMG and EXE are built automatically on EC2 at generation time.
# No Mac or Windows machine required.
# Download links appear in the Deploy Agents table within 30 seconds.
```

### End-user install — Mac (shell)

```bash
# Paste the link from your email
curl -fsSL "<presigned-url-from-email>" | bash
# Enter the 6-digit OTP from your email when prompted
```

### End-user install — Mac (DMG)

1. Click the DMG link in the Deploy Agents table or from the email.
2. Double-click the mounted DMG → double-click **PatronAI-Agent-Name.command**.
3. Terminal opens — enter your 6-digit OTP when prompted.

### End-user install — Windows (EXE)

Download the EXE from the Deploy Agents table. Double-click — PowerShell installer runs silently, enters OTP, installs hook and scan scheduler.

```powershell
# Or via PowerShell directly:
powershell -ExecutionPolicy Bypass -File setup_agent.ps1
```

### End-user install — Linux

```bash
curl -fsSL "<presigned-url-from-email>" | bash
# Enter the 6-digit OTP from your email when prompted
# Scan scheduled via crontab (*/30), heartbeat via crontab (*/5)
```

### Verify installation

```bash
cat ~/.patronai/config.json          # Mac/Linux — bucket, region, token
ls ~/.patronai/                      # config.json, heartbeat.sh, scan.sh, authorized_domains, …
# Windows: %USERPROFILE%\.patronai\config.json
```

Heartbeat fires within 5 minutes. Endpoint scan runs immediately on install, then every 30 min. Status visible in the Deploy Agents tab.

### Per-user authorised tools (whitelist)

Each user has an `authorized.csv` stored at `config/HOOK_AGENTS/{token}/authorized.csv`.
Scan findings matching any authorised domain or package name are suppressed — not flagged, not alerted.

To update without reinstalling: **Deploy Agents table → Whitelist button → edit → Save**.
The agent fetches the updated list from S3 on its next scan (≤ 30 min). No email, no reinstall, no action needed from the developer.

---

## Regression Testing

Run before every merge to main. Requires Docker and LocalStack.

```bash
# Full suite — unit + integration + docker build (~4 minutes)
bash scripts/run_regression.sh

# Keep LocalStack running after tests
bash scripts/run_regression.sh --keep-localstack

# Unit tests only — no LocalStack needed (~30 seconds)
bash scripts/run_regression.sh --unit-only

# Skip docker build check
bash scripts/run_regression.sh --no-docker-build
```

HTML report written to `reports/regression-YYYY-MM-DD-HHMMSS.html` after every run. Dark theme. Per-test pass/fail rows. Open in any browser.

**115 tests across 11 files:**

| File | Tests | Covers |
|---|---|---|
| `test_normalizer.py` | 10 | All 4 parsers — Packetbeat, VPC Flow, NAC, agent code signals |
| `test_matcher.py` | 12 | All 4 outcomes — authorized first, wildcard, port matching |
| `test_code_engine.py` | 12 | Dept scope, MCP patterns, 15 framework patterns, suppress logic |
| `test_code_analyser.py` | 10 | Qwen 3 analyse() — CRITICAL/LOW happy path, every fallback reroute (timeout, empty, bad JSON, model/CLI missing), is_available |
| `test_summarizer.py` | 9 | Polars aggregations, alert counts, top sources ranking |
| `test_backfill.py` | 10 | backfill() day count, empty skip, write-every-day contract, run_now today-default, cursor reset |
| `test_eni_filter.py` | 8 | EFS/NAT/VPCE/ELB/Lambda ENI types, customer ENI kept, cache-miss fail-open |
| `test_alerter.py` | 13 | Payload builder, SNS publish, Trinity POST, timeout, no-channels, independent channel failure |
| `test_settings.py` | 6 | ocsf_bucket empty-string fix, S3 read/write, env fallback |
| `test_render_agent_package.py` | 5 | Mac/Linux + Windows renders, S3 upload, unsupported OS, two-pass URL render |
| `test_hook_agents_prefix.py` | 4 | HOOK_AGENTS_PREFIX constant, catalog key, no bare agents/ paths |
| `test_pipeline.py` | 14 | Full S3 cycle via LocalStack — cursor, findings, dedup, summary |

Install test dependencies:

```bash
pip install pytest localstack-client --break-system-packages
```

---

## Performance

Dashboards read from summary/daily/ for all charts. Never touch raw logs.
Drill downs use S3 Select — filtering pushed to S3, not loaded into memory.
Polars (MIT) used for all dataframe operations. Memory stays under 200MB.
Grafana auto-scales 1-5 Fargate tasks behind ALB. Scanner stays fixed at 1 task.

---

## Multi-Cloud Lock-in

| Lock-in level | Services | Action to switch |
|---|---|---|
| HIGH (4) | VPC Flow Logs, IAM Identity Center, CloudTrail, EC2 describe | Code change in providers/aws/ → implement providers/gcp/ |
| MEDIUM (6) | S3, SNS, Parameter Store, Fargate, S3 Select, Kinesis | Config change only |
| LOW (5) | ECR, Docker image, Grafana, Streamlit, Polars | Zero change |

Set CLOUD_PROVIDER=gcp or CLOUD_PROVIDER=azure. Implement the providers/ adapter for that cloud. Core scanner unchanged.

---

## Residual Gaps

Four scenarios not fully detectable:

1. **Fully offline local inference** — model downloaded, data copied via USB, zero network call. The endpoint scan detects the installed package (e.g. `ollama`, `transformers`) and running process, but not the data exfiltration itself.
2. **Personal cloud accounts** — personal AWS/GCP with personal credit card, no corporate IAM. Out of scope for network layer.
3. **Web UI manual copy-paste** — developer manually copies data into ChatGPT browser tab. **Partially closed** by the endpoint scan browser history check (Safari, Chrome, Firefox, Edge) — the domain visit is flagged even if no data transfer is visible on the network.
4. **Personal laptop outside VPN** — device unmanaged, accepted company risk.

The **endpoint scan** (every 30 min) closes gaps partially for scenarios 1 and 3 on enrolled devices.
The **Marauder Scan** code layer (git pre-commit hook) closes the hardcoded key gap at commit time.
The **network layer** (VPC Flow Logs + Packetbeat) catches traffic to 70+ AI providers on the corporate network.
GenLock (separate product) closes browser and desktop AI tool usage gaps comprehensively.

---

## Licence

MIT. Open source stack throughout:
- Polars (MIT), Packetbeat (Apache 2.0), Zeek (BSD), Grafana (AGPL v3)
- ReportLab (BSD), Streamlit (Apache 2.0), boto3 (Apache 2.0)

---

PatronAI by Giggso Inc (Ravi Venugopal) · partners: TrinityOps.ai · AIRTaaS
