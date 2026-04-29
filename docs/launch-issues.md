# First GitHub Issues — OSS Launch Pack

These are the seed issues to create on GitHub when the repo goes public.
Copy/paste the title + body into GitHub Issues (or use `gh issue create`).

---

## Issue 1 — Good First Issue: Add detection for Mistral API

**Labels:** `provider-detection`, `good first issue`
**Milestone:** v1.2.0

**Title:** `[Detection] Add Mistral API (api.mistral.ai)`

**Body:**
```
Mistral AI (https://mistral.ai) provides cloud-hosted LLM APIs via api.mistral.ai.
This provider is not currently in providers_deny.csv.

**Traffic patterns to match:**
- TLS SNI: `api.mistral.ai`
- HTTP Host: `api.mistral.ai`
- URL prefix: `/v1/chat/completions`
- Authorization header: `Bearer sk-...`

**Suggested deny entry:**
api.mistral.ai,Mistral AI,cloud,HIGH,llm_api

This is a low-complexity addition — good for a first contribution.
See CONTRIBUTING.md for the provider rule format.
```

---

## Issue 2 — Good First Issue: Add detection for Groq Cloud

**Labels:** `provider-detection`, `good first issue`
**Milestone:** v1.2.0

**Title:** `[Detection] Add Groq Cloud (api.groq.com)`

**Body:**
```
Groq (https://groq.com) offers ultra-fast LLM inference at api.groq.com.
Not currently covered.

**Traffic patterns:**
- TLS SNI: `api.groq.com`
- URL prefix: `/openai/v1/chat/completions`

**Suggested deny entry:**
api.groq.com,Groq,cloud,HIGH,llm_api
```

---

## Issue 3 — Enhancement: Slack / Teams alert formatting

**Labels:** `enhancement`
**Milestone:** v1.1.0

**Title:** `[Enhancement] Improve Slack/Teams alert message formatting`

**Body:**
```
Current webhook alerts use a plain JSON body. It would be great to have:
- Slack Block Kit formatted messages (severity colour, user name, provider, device)
- Teams Adaptive Card format
- A configurable per-severity emoji prefix (🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM)

Relevant file: `ghost-ai-scanner/src/alerter.py`
```

---

## Issue 4 — Enhancement: CSV export from dashboard

**Labels:** `enhancement`
**Milestone:** v1.2.0

**Title:** `[Enhancement] CSV export button in Exec and Manager views`

**Body:**
```
The dashboard currently offers PDF report export (Reports tab) but no quick CSV.
A "Download CSV" button in the Exec and Manager views would let analysts pull
raw findings into Excel/Google Sheets without spinning up the full PDF pipeline.

Expected columns: timestamp, user_email, device, provider, severity, category, finding_id
```

---

## Issue 5 — Bug: Agent Fleet shows stale PENDING entries

**Labels:** `bug`

**Title:** `[Bug] Agent Fleet accumulates PENDING entries that are never cleaned up`

**Body:**
```
Every time an admin clicks "Generate Package" for the same user, a new catalog
token is created. Entries with status PENDING (package sent but never installed)
persist forever with no UI affordance to remove them.

**Fixed in v1.1.0** — revoke/delete button added in Support → Agent Fleet tab
with audit log. Closing for tracking only.
```

---

## Issue 6 — Documentation: Quickstart video walkthrough

**Labels:** `documentation`

**Title:** `[Docs] Add a 5-minute video walkthrough to README`

**Body:**
```
A short (3–5 min) screen recording showing:
1. docker compose up
2. Login to dashboard
3. Generating and deploying an agent
4. Viewing a finding in the Exec view
5. Running a PDF report

This dramatically lowers the barrier for evaluators.
Hosting suggestion: upload to YouTube → embed in README.
```

---

## CLI helper to create these issues

```bash
# Requires: gh auth login + public repo

REPO="giggso/patronai"   # update with actual org/repo

gh issue create --repo $REPO \
  --title "[Detection] Add Mistral API (api.mistral.ai)" \
  --label "provider-detection,good first issue" \
  --body-file docs/launch-issues.md
```

*(Run for each issue above — or use GitHub web UI.)*
