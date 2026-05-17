# PatronAI — CISO Gap Analysis vs Palo Alto AI Security
**Author:** Giggso Inc / Ravi Venugopal  
**Reviewed:** 2026-05-17  
**Raven:** v2.9.0  
**Status:** v2 Strategy — Giggso-native partners, no external commercial SaaS

---

## ⚡ Strategy Update — 2026-05-17

Original plan used Cloudflare Zero Trust, GreyNoise, and AWS Security Hub as external partners.
**Revised strategy:** zero external commercial dependencies. All gaps closed using:

| Gap | Original Partner | Revised Approach |
|---|---|---|
| Enforcement (Gap 1) | Cloudflare Zero Trust | AWS Route53 Resolver DNS Firewall + hook agent hosts-file |
| DLP (Gap 2) | Cloudflare Workers | Python proxy container in docker-compose.yml |
| SOAR Response (Gap 3) | AWS Lambda + EventBridge | **Prism7** (Giggso) via structured email — 90s IAM shutdown |
| Threat Intel (Gap 4) | GreyNoise + GitHub | AlienVault OTX (free) + GitHub + MITRE ATLAS (free) |
| SIEM (Gap 5) | AWS Security Hub → Splunk | **v2 only** — OpenSearch in docker-compose (open-source) |
| UEBA Anomaly (Gap 6) | Internal anomaly_score.py | **Log Analyzer** (Giggso) via S3 — PatronAI writes, Log Analyzer polls |
| Compliance (Gap 7) | Internal YAML | Internal YAML — unchanged |

**Integration model:**
- **Log Analyzer** reads `findings_current/` from S3 (PatronAI's compacted findings) → writes anomaly findings back to `anomalies/` prefix → PatronAI ingestor picks up on next scan cycle as `source="log_analyzer"`
- **Prism7** receives structured email from `src/notify/email.py` → parses subject + JSON body → runs playbook (IAM revoke, team alert, ticket) in 90 seconds
- **No Lambda, no EventBridge, no new AWS managed services** beyond Route53 Resolver DNS Firewall

---

## Executive Summary

PatronAI is a **surveillance and analytics platform** for AI governance. It detects, aggregates, scores, and reports on shadow AI usage across network, code, and endpoint surfaces.

Palo Alto's AI security stack (AI Access Security + Prisma Access + Cortex XSOAR + Unit 42) is **detect + enforce + respond + learn** — a full control loop.

PatronAI today covers the **detect** leg only. This document maps the seven capability gaps, proposes a partner-model approach to close each gap without infrastructure changes, and provides a drama-debate for each recommendation.

---

## The One-Line Truth

> PatronAI is a surveillance camera. Palo Alto is the door, the lock, the alarm, the guard, and the incident commander — all wired together.

---

## Current PatronAI Capability Map

| Layer | Capability | Code Location |
|---|---|---|
| Detection — network | VPC Flow Logs, Packetbeat, Zeek → domain match vs 70+ providers | `normalizer/`, `matcher/engine.py` |
| Detection — code | Git pre-commit → framework imports, API keys, MCP configs | `code_analyser.py`, `matcher/code_engine.py` |
| Detection — endpoint | Hook agent every 30 min → processes, pip, browser, IDE, Docker | `normalizer/agent_explode.py` |
| Aggregation | Polars daily summaries, 5-dim hourly rollup, signature compaction | `summarizer/`, `jobs/` |
| Scoring | Weighted 0–100 posture score, category multipliers | `scoring/risk_score.py` |
| Alert dispatch | SNS + Trinity webhook, 60-min dedup window | `alerter/dispatcher.py` |
| Authorization | Per-user approved provider list in S3 | `services/authorize.py` |
| **Response** | **None. Alert fires. Nothing else happens.** | — |
| **Enforcement** | **None. Traffic is never blocked.** | — |
| **DLP** | **None. Payload content never inspected.** | — |

---

## Palo Alto Gap Map

| Capability | Palo Alto | PatronAI Today | Gap Severity |
|---|---|---|---|
| Inline traffic blocking | Blocks before data leaves | Detects 30 min later | **CRITICAL** |
| DLP — payload inspection | Decrypts TLS, scans for PII/PHI/PAN/IP | Zero payload visibility | **CRITICAL** |
| Prompt inspection | Reads actual prompts, flags sensitive content | Cannot see prompts | **CRITICAL** |
| Automated response playbooks | XSOAR: disable account → ticket → notify manager | SNS alert only | **HIGH** |
| UEBA — behavioral baseline | Flags anomalies vs user's normal pattern | Every hit treated identically | **HIGH** |
| Threat intel feed | Unit 42 real-time, auto-discovers new AI providers | Static YAML, manual update | **HIGH** |
| SIEM integration | Splunk, Sentinel, QRadar out of box | None | **HIGH** |
| Application-layer policy | Allow ChatGPT browse, block ChatGPT file upload | Binary allow/block only | **HIGH** |
| CASB for SaaS AI | Controls Copilot, GitHub Copilot at OAuth level | Network domain only | **MEDIUM** |
| Device trust scoring | MDM compliance before granting AI access | No device trust | **MEDIUM** |
| Compliance mapping | NIST AI RMF, EU AI Act, GDPR Art.22 per finding | PDF reports only | **MEDIUM** |
| Incident case management | XSOAR cases, SLA tracking, escalation | No case concept | **MEDIUM** |

---

## Gap 1 — Inline Enforcement (CRITICAL)

### Problem
By the time PatronAI fires an alert, data is already at OpenAI. A 30-minute endpoint scan cycle means 30 minutes of undetected exfiltration per event.

### Revised Solution: AWS Route53 Resolver DNS Firewall (VPC) + Hook Agent hosts-file (endpoints)
Two-layer enforcement. VPC layer catches server-side traffic. Endpoint layer catches developer laptops. Both are AWS-native or in-product — no external partner.

### Implementation Plan

**Layer 1 — VPC: Route53 Resolver DNS Firewall**
1. **`jobs/dns_firewall_sync.py`** — reads `config/providers.yaml` + `unauthorized.csv`, calls `boto3.client('route53resolver')` to create/update a DNS Firewall domain list with all unauthorized AI provider domains. Runs hourly after rollup job.
2. **Firewall rule group** — associates domain list with customer VPC via `create_firewall_rule_group`. Action=BLOCK for unauthorized, Action=ALLOW for authorized. Idempotent — safe to re-run.
3. **Immediate unblock** — `services/dns_firewall.py:unblock_domain(domain)` calls Route53 Resolver API directly. Wired to "Unblock Now" button in dashboard.

**Layer 2 — Endpoint: Hook agent hosts-file enforcement**
1. **`scripts/enforce_hosts.py`** (runs inside hook agent on each scan cycle) — fetches current unauthorized domain list from `s3://patronai/config/enforcement_blocklist.json`, writes entries to `/etc/hosts` (macOS/Linux) or `C:\Windows\System32\drivers\etc\hosts` (Windows).
2. Requires hook agent running with elevated privileges (same privilege level as process scanning).
3. Entries written with `# patronai-managed` comment for clean removal on authorize.

### Architecture
```
PatronAI providers.yaml
        │
        ▼
dns_firewall_sync.py (hourly)
        ├── Route53 Resolver DNS Firewall (VPC — blocks EC2 / ECS / server-side)
        └── s3://patronai/config/enforcement_blocklist.json
                │
                ▼
            enforce_hosts.py (in hook agent, every 30 min)
                └── /etc/hosts update (developer laptops)
```

### Constraints
- Route53 Resolver DNS Firewall: ~$0.60/domain list/month + $0.60/million queries — negligible
- Hosts-file enforcement bypassed by hardcoded IP (rare) or personal hotspot (DNS bypass)
- Hosts-file updates need elevated privileges on endpoint — agent must run as admin/root
- Route53 Resolver scope is VPC only — does not protect traffic from on-prem or remote devices not using VPN

---

## Gap 2 — DLP / Payload Inspection (CRITICAL)

### Problem
PatronAI sees `api.openai.com:443` in flow logs. It cannot determine if the payload contains "explain Python loops" or the full customer database. Palo Alto decrypts TLS inline and scans the body.

### Revised Solution: Python DLP Proxy Container (docker-compose)
A lightweight HTTP proxy container runs alongside the PatronAI scanner in docker-compose. Developer endpoints that configure `HTTP_PROXY` / `HTTPS_PROXY` to point at this container have AI API calls intercepted and inspected before forwarding. No external service. No cloud cost. Zero new AWS infrastructure.

### Implementation Plan
1. **`services/dlp_proxy/proxy.py`** — aiohttp-based HTTP CONNECT proxy, listens on port 8080. Intercepts CONNECT tunnels to domains matching `providers.yaml`. Forwards all other traffic unmodified.
2. **`services/dlp_proxy/inspect.py`** — runs 4 regex patterns on decrypted request body:
   - PAN: `\b(?:\d{4}[\s-]?){3}\d{4}\b`
   - SSN: `\b\d{3}-\d{2}-\d{4}\b`
   - AWS key: `AKIA[0-9A-Z]{16}`
   - Bulk email (≥10 addresses in single payload — single address is context, not exfiltration)
   - Patterns reused from `matcher/code_engine.py` — no new regex invention
3. **On DLP hit** — proxy returns 403 + `X-PatronAI-Block: DLP-{pattern}` header + writes block event to `s3://patronai/findings/dlp/YYYY/MM/DD/{uuid}.jsonl`
4. **New ingestor source** — `source_hint="dlp_proxy"` normalizer reads block events from `findings/dlp/` into findings store with `category="dlp_block"`
5. **docker-compose.yml** — add `dlp-proxy` service (Python 3.13-slim, expose 8080). Endpoints set `HTTP_PROXY=http://patronai-proxy:8080` via MDM or dev onboarding doc.
6. **Opt-in by default** — proxy only intercepts domains in `providers.yaml`. Clean pass-through for all other traffic.

### Constraints
- Requires developer endpoints to configure proxy — cannot force without MDM (same constraint as any proxy solution)
- TLS inspection requires CA cert installed on developer machine — documented in onboarding guide
- Only catches API calls, not browser-based ChatGPT sessions (same limit as Palo Alto for browser traffic without SSL forward proxy)
- Zero managed service cost — fully containerized, runs on existing EC2

---

## Gap 3 — Automated Response / SOAR (HIGH)

### Problem
PatronAI fires SNS → human reads it in 4 hours → opens ticket → maybe revokes access. Palo Alto XSOAR runs a playbook in 90 seconds: disable account → create ticket → notify manager → add to watchlist.

### Solution: Prism7 (Giggso) via Structured Email
### ✅ `src/notify/email.py` with full SES `send()` already exists — this gap is ~20 lines of new code.

```
PatronAI dispatcher.py  →  send_prism7_alert()  →  SES  →  Prism7 inbound parser
                                                              │  playbook match
                                                              ▼
                                                   CRITICAL+PERSONAL_KEY → IAM revoke (90s)
                                                   CRITICAL → Slack + PagerDuty
                                                   HIGH → manager DM + ticket
                                                   Any → s3://patronai/incidents/{uuid}.json
```

### What's Left (PatronAI side — ~20 lines total)
1. **`src/notify/email.py`** — add `send_prism7_alert(finding: dict) -> bool`:
   - Subject: `[PatronAI:{severity}] {outcome} | {owner} → {provider}`
   - Body: OCSF finding dict serialized as JSON
   - To: `PRISM7_INBOUND_EMAIL` from `.env`
   - Calls existing `send()` — zero new SES logic
2. **`alerter/dispatcher.py`** — add `results["prism7"] = _fire_prism7(finding)`. Guard: only fires if `PRISM7_INBOUND_EMAIL` set in `.env`.

### What Prism7 Handles (zero PatronAI work)
- All playbook logic: IAM revoke, Slack, PagerDuty, Jira tickets, confirm mode
- Writing incident records back to `s3://patronai/incidents/`
- The 90-second SLA

### Constraints
- Prism7 deployed independently — PatronAI has no visibility into its execution
- If Prism7 is down, SNS still fires as fallback — silent SOAR failure is acceptable
- All playbook config lives in Prism7, not PatronAI — clean separation

---

## Gap 4 — Threat Intelligence (HIGH)

### Problem
PatronAI's provider list is a static YAML. When a new AI provider launches tomorrow, PatronAI is blind until someone manually edits `providers.yaml`. Palo Alto Unit 42 pushes updates in real-time.

### Revised Solution: AlienVault OTX + GitHub + MITRE ATLAS (all free, no account for some)

### Implementation Plan
1. **`jobs/threat_intel_refresh.py`** — nightly job, three free sources:
   - **AlienVault OTX** (free API, 10k req/day — permanent free tier): `GET /api/v1/indicators/domain/{domain}/reputation` to classify new unknown domains from findings. API key in `.env` as `OTX_API_KEY`. No credit card required.
   - **GitHub search API**: search for new MCP server registrations (`"mcpServers"` in JSON). Extract and cross-reference domains against `providers.yaml`. Use `GITHUB_TOKEN` in `.env` for 5000 req/hour (vs 60 unauthenticated).
   - **MITRE ATLAS** (`atlas.mitre.org/data/ATLAS.yaml` — public GitHub, no auth): download nightly. Parse adversarial ML technique IDs → map to PatronAI `outcome` values. Auto-tag findings with ATLAS technique IDs (e.g., `AML.T0047` — ML Supply Chain Compromise).
   - **URLhaus** (free): check new domains against phishing/malware blocklist.
2. **Multi-source threshold** — domain only auto-added to `providers.yaml` if seen in ≥2 independent sources. Single-source additions go to `config/pending_intel.yaml` for weekly human review.
3. **`config/atlas_map.yaml`** — maps PatronAI `outcome` values to ATLAS technique IDs. Shown on finding detail panel in dashboard.
4. **Auto-PR gate** — new `providers.yaml` entries committed on branch `chore/intel-refresh-{date}` with `[INTEL:AUTO]` tag. Operator reviews weekly via PR.
5. **GuardDuty import** — GuardDuty findings → SNS → PatronAI ingestor as `source="guardduty"`. Ships in same sprint as threat intel job (shared infrastructure).

### Constraints
- AlienVault OTX: free account registration required once. No rate-limit issues at PatronAI scale.
- GitHub token optional but strongly recommended — unauthenticated rate limit (60/hr) is insufficient for nightly enrichment
- MITRE ATLAS YAML is a weekly release cadence — nightly download is safe, content changes slowly
- Multi-source threshold prevents poisoned intel injection from any single malicious or misconfigured source

---

## Gap 5 — SIEM Integration (HIGH)

### Problem
Enterprise security teams run Splunk or Microsoft Sentinel. PatronAI findings live in S3. No bridge exists. This is a top-3 enterprise buying objection.

### Revised Solution: Deferred to v2 — OpenSearch in docker-compose

### v1 Decision
SIEM integration is deferred from v1. Enterprise customers that need a SIEM bridge today are unblocked via S3: any SIEM with an S3 connector (Splunk, Sentinel, QRadar) can be configured to read `s3://patronai/findings_current/` directly — standard configuration that the customer's SIEM team already knows. PatronAI documents the S3 path and schema in the operator guide. No code changes required.

### v2 Plan: Self-Hosted OpenSearch in docker-compose
1. **`docker-compose.yml`** — add `opensearch` service (single-node, opensearch:2.x, 2GB heap). Add `opensearch-dashboards` service (Kibana-compatible UI). Both run on existing EC2.
2. **`services/opensearch_writer.py`** — after each findings compact cycle, writes new findings to index `patronai-findings-{YYYY.MM.DD}`. ILM policy: 90-day retention, auto-delete older indices.
3. **SIEM connectors**: Splunk (OpenSearch plugin), Microsoft Sentinel (Azure Monitor via Logstash), QRadar (DSM for Elasticsearch-compatible sources) all have native connectors — PatronAI needs zero per-SIEM code.
4. **OpenSearch Dashboards** (bundled, zero extra cost): provides Kibana-grade search/visualization for customers without a corporate SIEM.

### Constraints
- OpenSearch 2GB heap requires EC2 t3.medium minimum — evaluate RAM headroom before v2 planning
- Single-node OpenSearch has no replication — acceptable for governance/audit use case, not SOC-grade
- Adds docker-compose service operational complexity — not acceptable for v1 scope
- v2 target: after PatronAI v1 is validated in production with ≥3 customers

---

## Gap 6 — Behavioral Baseline / UEBA (HIGH)

### Problem
PatronAI treats a user's first-ever hit on `api.openai.com` at 3am from a new country identically to their daily normal call from the office. Palo Alto flags the anomaly. PatronAI doesn't.

### Solution: Log Analyzer (Giggso) via S3
### ✅ `findings_compact.py` already writes `findings_current/YYYY/MM/DD/by_signature.jsonl` to S3. PatronAI's side of the data contract is already fulfilled.

```
✅ PatronAI jobs/findings_compact.py
    └── already writes → s3://patronai/findings_current/YYYY/MM/DD/by_signature.jsonl

Log Analyzer (separate Giggso product — zero PatronAI work on this side)
    ├── polls findings_current/ (read-only IAM role)
    ├── runs anomaly detection
    └── writes → s3://patronai/anomalies/YYYY/MM/DD/{batch}.jsonl

PatronAI log_analyzer_reader.py  ←  reads anomalies/  ←  new ingestor (small)
```

### What's Left (PatronAI side — one new ingestor module)
1. **`src/ingestor/log_analyzer_reader.py`** — reads `s3://patronai/anomalies/` using `CursorStore` (same pattern as every other ingestor). Normalizes to OCSF schema with `source="log_analyzer"`, `category="anomaly"`. Skips malformed JSON (log + continue).
2. **Severity mapping** — `source=="log_analyzer"` → auto-set severity=HIGH.
3. **Dashboard badge** — "AI Anomaly" badge on risk card for `source=log_analyzer` findings.
4. **IAM role doc** — Log Analyzer gets read-only on `findings_current/`, write-only on `anomalies/`. Document in operator guide.

### S3 Contract (PatronAI reads this format from Log Analyzer)
```json
{"anomaly_id": "uuid", "user_email": "user@corp.com",
 "anomaly_type": "VOLUME_SPIKE|OFF_HOURS|NEW_PROVIDER|GEO_ANOMALY",
 "provider": "openai", "detected_at": "ISO-8601",
 "baseline_value": 12, "observed_value": 147, "confidence": 0.91}
```

### What Log Analyzer Handles (zero PatronAI work)
- All anomaly detection logic, baselines, timezone-aware off-hours, geo-resolution
- Dedup of its own output
- Its own polling schedule

### Constraints
- No Log Analyzer deployed = no UEBA (feature gracefully absent, not broken — no crash)
- IAM setup required once per customer deployment

---

## Gap 7 — Compliance Framework Mapping (MEDIUM)

### Problem
PatronAI generates PDFs. A CISO presenting to the board or auditor needs to say "we are NIST AI RMF Govern 1.1 compliant" not "here is a SHA-256 hash." PatronAI doesn't speak that language.

### Solution: Config YAML + reporter extension (internal — unchanged from original plan)

### Implementation Plan
1. **`config/compliance_map.yaml`**:

```yaml
version: "1.0"
last_reviewed: "2026-05-16"
frameworks:
  NIST_AI_RMF:
    GOVERN_1_1:
      description: "Policies for AI risk management"
      triggers: ["UNAUTHORIZED", "DOMAIN_ALERT"]
    MAP_2_1:
      description: "AI risk assumptions documented"
      triggers: ["mcp_server", "agent_workflow"]
  EU_AI_ACT:
    Article_9:
      description: "Risk management for high-risk AI"
      triggers: ["CRITICAL", "HIGH"]
  GDPR:
    Article_22:
      description: "Automated decision-making / AI profiling"
      triggers: ["agent_scheduled", "process"]
  SOC2:
    CC6_1:
      description: "Logical access security"
      triggers: ["PERSONAL_KEY", "UNAUTHORIZED"]
```

2. **`reporter/data_builder.py` extension** — `build_compliance_annex(store, days, compliance_map)` tags each finding with matching controls.
3. **R6 compliance report** in `dashboard/ui/reports/r6_compliance.py` gains a "Controls Coverage" table showing which controls have findings evidence and which are uncovered.

### Constraints
- NIST AI RMF 1.0 was released Jan 2023. NIST AI RMF 2.0 is in draft — mapping will need update
- EU AI Act enforcement began Feb 2025 — some Articles still lack implementing regulations
- YAML compliance map needs a review timestamp and a versioning discipline

---

## Priority Roadmap

| Sprint | Gap | Approach | Real Effort | CISO Impact |
|---|---|---|---|---|
| **1** | Gap 3 — SOAR | Prism7 — 20 lines wired to existing email.py | **0.5 days** ✅ already built | Automated remediation in 90 seconds |
| **1** | Gap 1 — DNS Enforcement | Route53 DNS Firewall + hosts-file agent | **4.5 days** | Blocks exfil at VPC + endpoint layer |
| **2** | Gap 2 — DLP Proxy | Python proxy container in docker-compose | **5 days** | Payload inspection, AWS key / PAN blocking |
| **2** | Gap 4 — Threat Intel | AlienVault OTX + GitHub + MITRE ATLAS | **4 days** | Self-updating provider list, ATLAS tagging |
| **3** | Gap 6 — UEBA | Log Analyzer via S3 — one new ingestor reader | **1.75 days** ✅ S3 write already done | Behavioral anomaly detection |
| **3** | Gap 7 — Compliance | Config YAML + reporter extension | **2.5 days** | NIST AI RMF / EU AI Act audit-ready |
| **v2** | Gap 5 — SIEM | OpenSearch in docker-compose | **2.5 days** | Enterprise SIEM compatibility |

**v1 total: ~18 engineering days of net-new code. Gap 3 and Gap 6 infrastructure already exists — just wiring.**

---

## The Hard Limit

**Inline TLS decryption for browser traffic cannot be closed without infrastructure change.**

When a user opens ChatGPT in a browser and types a prompt, PatronAI sees a connection to `chat.openai.com`. The DLP proxy container only catches API calls routed through it via `HTTP_PROXY`. A user hitting ChatGPT's website directly bypasses everything — browser traffic does not honor `HTTP_PROXY` env vars.

Palo Alto closes this with SSL Forward Proxy — MITM at network layer, decrypt → inspect → re-encrypt. That requires either an NGFW appliance or Prisma Access. Without that infrastructure, the only mitigation is DNS blocking (Gap 1: Route53 DNS Firewall) which blocks the domain entirely rather than inspecting the payload. PatronAI v1 accepts this gap honestly: payload inspection covers API traffic only, not browser sessions.

---

*PatronAI CISO Gap Analysis — Giggso Inc — 2026-05-16*

---

# Drama Discussions

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ANDIE — DRAMA MODE
  Topic: PatronAI CISO Gap Debates (Gaps 1–7)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Mode:    Drama
  Panel:   5 personas
  Rounds:  2 per gap (14 total)
  Output:  Stress-tested recommendations + verdicts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Panel:
  Bruce   (CISO, F500 — security absolutist, hates surveillance theater)
  Meera   (Staff Engineer, PatronAI — knows every constraint in the code)
  Seibel  (Startup advisor — velocity, cost, GTM realism)
  Fatima  (AI Security researcher, ex-Unit 42 — adversary-first thinking)
  Ravi    (Founder / decision-maker — owns the roadmap and the P&L)
```

---

## Debate 1 — DNS Enforcement (Gap 1)

> ⚡ **Post-debate strategy:** Original proposal used Cloudflare Zero Trust Gateway. Revised approach: AWS Route53 Resolver DNS Firewall (VPC) + hook agent hosts-file enforcement (endpoints). Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** The proposal is to use Cloudflare Zero Trust Gateway to block unauthorized AI domains. 3-day sprint. Sounds clean. Is it?

**Round 1**

Bruce (CISO): This is the most important gap on the list. Detection-only security is a compliance checkbox, not a security posture. If I'm a CISO and I hear "we detect it 30 minutes after it happens," I'm not buying. Cloudflare Zero Trust is the right call — it's proven, it's cheap, and it closes the data-exfil window from 30 minutes to 0.

Meera (Engineer): I agree on the direction but not the 3-day estimate. The cloudflare_sync.py job that converts providers.yaml into Gateway DNS policies — that's 1 day. But WARP client rollout is not a 1-day thing. That's MDM, and every corporate MDM setup is different. Jamf, Intune, Kandji — each one needs a tested config profile. We can't own that timeline.

Seibel (Advisor): Meera's right on the WARP issue, but I want to flag something bigger. The moment PatronAI starts blocking traffic — not just detecting it — we've crossed from "observability tool" to "network enforcement tool." That changes the sales motion entirely. Some customers will love it. Some IT teams will reject it as overreach. Have we thought about how we position this?

Fatima (Security): I'll add the adversary angle. DNS-level blocking is trivially bypassed by any user who sets a custom DNS server on their machine or uses a personal hotspot. If the threat model is a malicious insider or a sophisticated user, Cloudflare DNS alone doesn't hold. The WARP client is necessary but not sufficient — you'd also need to enforce that WARP is running via a device compliance check.

Ravi (Founder): OK so the Cloudflare sync job — we ship that. That's the low-hanging fruit. WARP client rollout we document and provide a config profile template, but we don't own the MDM push. Agreed on the sales positioning — we make enforcement opt-in per-tenant. Security teams who want it, turn it on. Observability-only customers don't have to. Fatima, the bypass concern is real — we document it honestly in the CISO guide.

**Round 1 Verdict:** ✅ Ship cloudflare_sync.py as planned. 🔴 Revise estimate — WARP client is customer-owned MDM push, not in our 3-day scope. Add bypass caveat to gap doc.

---

**Round 2**

Fatima (Security): One more thing on enforcement: what happens when PatronAI blocks a domain and it turns out to be a false positive? Say a developer's company legitimately uses an AI provider we flagged as unauthorized. They get DNS-blocked. Who do they call? The IT helpdesk will get flooded.

Meera (Engineer): We already have the authorization flow in authorize.py. If a domain is in a user's authorized list, we exclude it from the Cloudflare block. The problem is the sync latency — if someone gets authorized in PatronAI's dashboard, the Cloudflare exclude rule updates on the next hourly sync. That's up to a 59-minute wait while blocked.

Bruce (CISO): 59 minutes for a false-positive unblock is unacceptable operationally. You'd have the CISO's phone ringing. We need a manual "unblock now" button in the dashboard that triggers an immediate Cloudflare API call, not waiting for the hourly sync.

Seibel (Advisor): That's a 4-hour feature, not a 3-day sprint item. Add it to sprint 1 as a required deliverable. Without it, don't ship enforcement.

Ravi (Founder): Agreed. Sprint 1 must include: cloudflare_sync.py hourly job + immediate-unblock API call from dashboard. Gate the enforcement feature behind a settings toggle so cautious customers can observe-only.

**Round 2 Verdict:** ✅ Add immediate-unblock UI action as hard requirement before enforcement ships. Gate enforcement via settings.json tenant flag.

---

## Debate 2 — DLP / Proxy Inspection (Gap 2)

> ⚡ **Post-debate strategy:** Original proposal used Cloudflare Workers. Revised approach: Python DLP proxy container in docker-compose (aiohttp, port 8080). Same 4 regex patterns, zero external dependency. Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** The DLP proposal routes AI API calls through a Cloudflare Worker that inspects the request body for PAN, SSN, AWS keys, and email lists. 5-day estimate. This one has more moving parts.

**Round 1**

Meera (Engineer): The 10ms CPU time limit on Cloudflare Workers is a real constraint. A large OpenAI API request body with a document pasted into the prompt can be 128KB. Running 5 regex patterns across 128KB in 10ms is marginal. I've tested similar things — it's doable for simple patterns but we'd need to benchmark before shipping.

Bruce (CISO): I'd rather have 80% DLP coverage that's fast than 100% coverage that times out and fails open. If the Worker times out and forwards the request anyway, the user thinks they bypassed nothing. That's fine. What's NOT fine is failing closed — blocking legitimate requests because the Worker CPU-timed-out.

Fatima (Security): The bigger problem with this approach is that the user has to route their API calls through your gateway. Enterprise developers who know what they're doing will call `api.openai.com` directly. Unless you also have the Cloudflare Zero Trust layer (Gap 1) that forces all traffic through the proxy, the DLP Worker only catches people who are voluntarily using the approved gateway. That's self-selection bias — the compliant users get inspected, the non-compliant ones skip it entirely.

Seibel (Advisor): Fatima just described why the order matters. Gap 1 (enforcement) has to ship before Gap 2 (DLP) or you're building DLP on a foundation with a giant hole.

Ravi (Founder): That resequencing is correct. The roadmap should say: Gap 1 must be live before Gap 2 is useful. Document that dependency explicitly. For the Worker timeout concern — we test on P99 payload sizes in staging before shipping to prod. If we can't hit 10ms, we strip the payload to the first 50KB only. Signal is in the first few KB of a prompt anyway.

**Round 1 Verdict:** 🔴 Hard dependency: Gap 1 (enforcement) must ship first or DLP is theater. ⚠️ Worker CPU limit needs benchmark before commit. ✅ Fail-open is correct behavior on timeout.

---

**Round 2**

Bruce (CISO): I want to push on the regex patterns. PAN and SSN are well-understood. But "email lists" as a DLP trigger is going to generate enormous noise. Every API call that includes a user's email address for context will fire. We need to differentiate "single email in context" from "bulk email list exfiltration."

Fatima (Security): The threshold should be more than 10 email addresses in a single payload. A single email is context. 10+ emails is a list. That's a reasonable heuristic and it's cheap to implement — count regex matches, not just detect presence.

Meera (Engineer): I'll also flag that AWS key detection via `AKIA` prefix is already in our code_engine.py for git scanning. We can reuse the same pattern. The DLP Worker can literally import the same regex set. Good — we're not inventing new patterns, just applying existing ones at a new interception point.

Ravi (Founder): Consensus: DLP ships with 4 patterns (PAN, SSN, AWS key, bulk email 10+). Internal IP ranges are a stretch — drop from v1. Reuse code_engine.py patterns. Benchmark Worker on P99 payload size in staging. Document Gap 1 as hard dependency.

**Round 2 Verdict:** ✅ Ship 4 patterns (drop internal IP from v1). ✅ Reuse code_engine.py regex. ✅ Benchmark required before prod. ✅ Document Gap 1 dependency in WBS.

---

## Debate 3 — Automated Response / SOAR (Gap 3)

> ⚡ **Post-debate strategy:** Original proposal used AWS Lambda + EventBridge. Revised approach: Prism7 (Giggso) via structured email — PatronAI sends JSON email, Prism7 parses and executes playbook in 90 seconds. S3 action queue pattern preserved. Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** Lambda playbook that auto-revokes users, blocks IPs, creates Jira tickets. The "confirm mode" is proposed as a safety valve. Is it enough?

**Round 1**

Seibel (Advisor): The confirm mode is the right call for early deployment but I want to be honest — most security teams will leave it in confirm mode forever. Auto-response requires a level of trust in the detection accuracy that takes 6+ months to build. Don't sell this as "ship in sprint 1 and graduate to auto-execute." Plan for confirm mode to be the default for 12 months.

Bruce (CISO): I disagree on the timeline. For PERSONAL_KEY findings — when a hardcoded AWS access key is detected — there should be zero debate. Auto-revoke immediately. The cost of a false positive on a PERSONAL_KEY finding is negligible compared to the cost of a real credential leak. Split the confirm/auto logic by finding type, not by global setting.

Fatima (Security): Bruce is right on PERSONAL_KEY. And I'd add MCP_CONFIG_CHANGED to the auto-execute list. An unknown MCP server appearing on a corporate endpoint is either a supply chain attack or a policy violation — either way, immediate response is appropriate. The ambiguous cases (DOMAIN_ALERT, ENDPOINT_SCAN) are where confirm mode belongs.

Meera (Engineer): The Lambda approach is architecturally sound. My concern is secrets management. The Lambda needs Jira tokens, Slack tokens, Cloudflare API keys. These can't go in Lambda env vars as plaintext. We need AWS Secrets Manager. That's not a big lift but it needs to be in the WBS explicitly.

Ravi (Founder): Decision: auto-execute for PERSONAL_KEY and MCP_CONFIG_CHANGED from day one. Confirm mode for everything else, graduating to auto after 90 days of tuning. All credentials in Secrets Manager — add that as a task in sprint 1.

**Round 1 Verdict:** ✅ Split auto/confirm by finding type (not global toggle). ✅ PERSONAL_KEY + MCP_CONFIG_CHANGED → auto-execute immediately. ✅ All Lambda credentials via Secrets Manager — mandatory, not optional.

---

**Round 2**

Meera (Engineer): One more concern: the Lambda needs to call back into PatronAI's EC2 instance to trigger the authorize.py revoke. That's an inbound HTTP call to EC2. Right now EC2 has no authenticated API endpoint — it only talks outbound to S3. We'd need to expose a lightweight API, or better, have the Lambda write a "revoke pending" record to S3 that the EC2 container polls.

Bruce (CISO): Polling introduces latency. If the response playbook writes to S3 and EC2 picks it up on its 30-second scanner cycle, the effective revoke latency is up to 30 seconds. That's acceptable for most scenarios.

Seibel (Advisor): And it's architecturally cleaner. No inbound port on EC2, no authentication on the EC2 API surface. Lambda writes `s3://patronai/actions/revoke/{email}.json`, EC2 scanner reads it on next tick. Simple, secure, no new attack surface.

Ravi (Founder): That's the right call. Lambda → S3 action queue → EC2 scanner picks up. No inbound API on EC2. Add that design to the implementation spec.

**Round 2 Verdict:** ✅ Response actions via S3 action queue, not direct API call to EC2. Eliminates new attack surface. Maximum 30-second revoke latency — acceptable.

---

## Debate 4 — Threat Intelligence Refresh (Gap 4)

> ⚡ **Post-debate strategy:** GreyNoise replaced with AlienVault OTX (free, 10k req/day). MITRE ATLAS added as third free source. Multi-source threshold and auto-PR gate retained. Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** GreyNoise + GitHub scrape to auto-update providers.yaml. Auto-PR gate for human review.

**Round 1**

Fatima (Security): I need to be direct about GreyNoise Community API. 1000 requests per day is nothing. If PatronAI has 50 customers each seeing 20 new unknown domains per day, that's 1000 requests just for enrichment — one customer's full daily quota. The community tier is for hobby projects. Enterprise customers need either GreyNoise Business ($500+/month) or a different approach.

Bruce (CISO): Fatima's right, but let's not throw the baby out. The use case isn't "query GreyNoise for every domain." The use case is "when PatronAI sees a domain with zero match in providers.yaml — query once, cache result, don't re-query same domain for 7 days." That dramatically reduces API calls. 1000 net-new unknown domains per month across all customers is a realistic target.

Seibel (Advisor): The GitHub MCP server scrape is underrated in this proposal. The MCP ecosystem is growing faster than any static list can track. Every week there are 50+ new MCP servers registered. A nightly GitHub search for `"mcpServers"` is genuinely valuable signal, and it's free.

Meera (Engineer): The auto-YAML-update with PR gate is clever but has a poisoned intel risk that wasn't fully addressed. What prevents a malicious actor from creating a GitHub repo with a fake "mcpServers" config pointing to a legitimate domain, causing PatronAI to block it? We need a reputation threshold — only add domains that appear in multiple independent sources.

Ravi (Founder): Multi-source requirement is the right control. A domain only gets added to providers.yaml automatically if it appears in ≥2 sources (e.g., GreyNoise + GitHub, or URLhaus + GitHub). Single-source additions go to a "pending review" YAML for human approval. That closes the injection risk.

**Round 1 Verdict:** ⚠️ GreyNoise community tier is insufficient at scale. Design for GreyNoise Business or use sparingly with 7-day domain caching. ✅ GitHub MCP scrape is high-value, ship it. ✅ Multi-source threshold required to prevent poisoned intel injection.

---

**Round 2**

Fatima (Security): GuardDuty import is excellent and I want to make sure it doesn't get deprioritized. GuardDuty already watches VPC Flow Logs independently. When GuardDuty fires a UnauthorizedAccess:IAMUser/InstanceCredentialExfiltration finding, PatronAI should import it as a CRITICAL finding automatically. There's no overlap — GuardDuty covers threat behavior, PatronAI covers AI usage behavior. They're complementary layers.

Bruce (CISO): Agreed. And GuardDuty is already enabled in most AWS accounts. This is the cheapest integration on the list — it's just subscribing to an SNS topic that GuardDuty publishes to.

Meera (Engineer): Implementation is simple: GuardDuty findings → EventBridge → SNS → PatronAI ingestor Lambda → findings store with `source="guardduty"`. Same Lambda as the SOAR response, just a different handler.

Ravi (Founder): GuardDuty import moves to Sprint 3 alongside the threat intel job. They share the same infrastructure. One sprint, two deliverables.

**Round 2 Verdict:** ✅ GuardDuty import is low-effort, high-signal — ship with threat intel refresh sprint. Same Lambda infrastructure.

---

## Debate 5 — SIEM Integration (Gap 5)

> ⚡ **Post-debate strategy:** AWS Security Hub deferred entirely. v1 ships with documented S3 path for customer-owned SIEM connectors. Full SIEM integration moves to v2 via self-hosted OpenSearch in docker-compose. Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** 1-day effort, ASFF format, fans out to Splunk/Sentinel/QRadar. Sounds too easy. Is it?

**Round 1**

Bruce (CISO): This is the highest enterprise sales impact item on the list. Every enterprise CISO's first question when evaluating a security tool is "does it integrate with our SIEM?" If the answer is no, the evaluation ends. This must ship before any enterprise sales conversation.

Seibel (Advisor): The 1-day estimate is aggressive. ASFF format translation is mechanical — that's 1 day. But "validate Splunk connector" and "validate Sentinel connector" are not 1-day items. Each requires spinning up a test Splunk instance, configuring the Security Hub add-on, verifying the findings land correctly, and documenting the configuration steps for customers. That's 2 days per SIEM, minimum.

Meera (Engineer): Seibel's right. The PatronAI code change is 1 day. Customer-facing integration documentation and validation is a separate work package. I'd split the task: "security_hub.py + ASFF translation" = 1 day dev. "Integration validation + customer docs" = 3 days. Total: 4 days, two owners (dev + technical writer).

Fatima (Security): One nuance: Security Hub charges per finding imported. At $0.001/finding, a customer with 5000 findings/day pays $1825/year just for the SIEM bridge. That's not nothing for a startup customer. We should let customers configure a severity filter — only send CRITICAL+HIGH to Security Hub, filter out MEDIUM and LOW. That cuts cost by ~80% for most deployments.

Ravi (Founder): Add severity filter to security_hub.py as a config option. Document the cost math in the operator guide so customers aren't surprised. Revised estimate: 1 day dev + 3 days integration validation.

**Round 1 Verdict:** ✅ Ship it — highest enterprise impact per effort. 🔴 Revise estimate to 4 days total. ✅ Severity filter required for cost control. ✅ Split dev vs. validation/docs as separate tasks.

---

**Round 2**

Meera (Engineer): I want to raise something for Sentinel specifically. Microsoft Sentinel's AWS Security Hub connector requires a Log Analytics workspace and specific IAM permissions. A lot of enterprise customers use Sentinel because they're Microsoft shops — Office 365, Teams, Azure AD. But their AI workloads might be on AWS. Bridging AWS Security Hub to Azure Sentinel needs an Azure Logic App or an AWS Lambda forwarding to Azure Monitor. It's not as plug-and-play as the Splunk add-on.

Bruce (CISO): The 40% of enterprise customers on Azure is real. We should document the Sentinel path clearly even if it's more complex. The ASFF JSON can be forwarded to Azure Monitor via an HTTP Data Collector API — it doesn't need Security Hub as the intermediary. A customer on Azure can have the PatronAI alerter write ASFF directly to Azure Monitor.

Seibel (Advisor): Don't over-engineer v1. Ship Splunk integration first — it's the dominant enterprise SIEM. Document Sentinel as "supported via Azure Monitor HTTP API" with a reference architecture. Let a customer who needs it pull us toward validating it properly.

Ravi (Founder): Ship Splunk. Document Sentinel path as reference architecture. QRadar on the roadmap, not sprint 2.

**Round 2 Verdict:** ✅ Sprint 2: Splunk validated. ✅ Sentinel: reference architecture documented only. ⏳ QRadar: backlog.

---

## Debate 6 — UEBA / Behavioral Baseline (Gap 6)

> ⚡ **Post-debate strategy:** Internal `anomaly_score.py` replaced by Log Analyzer (Giggso) via S3. PatronAI writes `findings_current/` → Log Analyzer polls → writes `anomalies/` → PatronAI ingestor reads `source="log_analyzer"`. Clean decoupling. 14-day grace period and NEW_PROVIDER-first phasing retained. Debate below reflects original analysis; verdicts updated in summary table.

**Scene:** anomaly_score.py using existing 30-day rollup data. Flags: NEW_PROVIDER, OFF_HOURS, VOLUME_SPIKE, GEO_ANOMALY.

**Round 1**

Fatima (Security): 30-day baseline for UEBA is weak. Real UEBA tools — Securonix, Exabeam, Microsoft Sentinel UEBA — use 90-day baselines minimum, with seasonal adjustments. A user who works remotely from a different timezone every January will trigger OFF_HOURS every January with a 30-day baseline. The baseline will never converge for traveling employees.

Bruce (CISO): The nuance matters here. UEBA for AI usage specifically is different from UEBA for general network behavior. An employee's ChatGPT usage pattern is less variable than their network traffic pattern. The question isn't "is this normal for this user" — it's "has this user ever used this AI provider before?" NEW_PROVIDER is the highest-signal flag and it has zero baseline requirement. You know instantly on day one.

Seibel (Advisor): Bruce is making the right distinction. Ship NEW_PROVIDER in sprint 3. Everything else (OFF_HOURS, VOLUME_SPIKE, GEO_ANOMALY) needs baseline data and timezone infrastructure that we don't have yet. Phase the feature: v1 = NEW_PROVIDER only. v2 = remaining flags after 90 days of data.

Meera (Engineer): GEO_ANOMALY has a data quality problem I didn't raise before. The `geo_country` field in our schema is populated from VPC flow log destination geo, not source geo. We're seeing where the AI provider is, not where the user is. For GEO_ANOMALY we need source IP geo-resolution, which requires a GeoIP database. MaxMind GeoLite2 is free and we should add it. But it's another dependency.

Ravi (Founder): Sprint 3 ships: NEW_PROVIDER flag only, no baseline required. MaxMind GeoLite2 added as a dependency for future GEO_ANOMALY flag. All other UEBA flags go in v2 milestone after 90 days of production data.

**Round 1 Verdict:** ✅ Ship NEW_PROVIDER in sprint 3 — zero baseline required, highest signal. 🔴 OFF_HOURS, VOLUME_SPIKE, GEO_ANOMALY → v2 milestone. ✅ MaxMind GeoLite2 as dependency for future geo flags.

---

**Round 2**

Fatima (Security): Even NEW_PROVIDER will have a false-positive problem at onboarding. When a new customer installs PatronAI, every provider their employees have ever used is "new" for the first scan. You'll generate hundreds of NEW_PROVIDER alerts on day one of installation. That ruins the onboarding experience.

Meera (Engineer): We can solve this with an "onboarding grace period" — for the first 14 days, NEW_PROVIDER is logged but doesn't generate an alert. It's used to build the initial baseline only. After 14 days, NEW_PROVIDER alerts are live.

Bruce (CISO): 14 days is the right number. It's long enough to capture a typical employee's full AI toolset but short enough that security teams don't feel blind for too long.

Seibel (Advisor): And the 14-day grace period findings should still be visible in the dashboard — just marked with a "Baseline Building" badge so the security team can review them. Useful intelligence, just not alert-worthy yet.

Ravi (Founder): Add onboarding grace period to the spec: 14-day muted baseline period, configurable via settings.json. Findings visible but not alerted. Badge in dashboard.

**Round 2 Verdict:** ✅ 14-day onboarding grace period before NEW_PROVIDER alerts go live. ✅ Findings visible during grace period with "Baseline Building" badge. Configurable in settings.json.

---

## Debate 7 — Compliance Framework Mapping (Gap 7)

**Scene:** compliance_map.yaml + reporter extension. NIST AI RMF, EU AI Act, GDPR, SOC2. 2-day estimate. Lowest technical risk, highest board-room visibility.

**Round 1**

Bruce (CISO): This is the feature that gets PatronAI into board-level conversations. Every CISO is being asked by their board "how are we managing AI risk?" The answer today is anecdotal. With compliance mapping, the answer is "we have N findings mapped to NIST AI RMF GOVERN 1.1 this quarter, here is the evidence." That changes the product from a security tool to a governance tool. Very different price point.

Seibel (Advisor): Agreed on the strategic value, but I want to push back on the static YAML approach for the long term. Regulations change. NIST AI RMF 2.0 is in draft. EU AI Act is still publishing implementing regulations. A YAML that becomes stale is worse than no mapping at all — it gives false confidence to a CISO presenting wrong control evidence to an auditor.

Fatima (Security): The versioning concern is real but solvable. Every compliance framework has a version number. The YAML includes `framework_version: "NIST AI RMF 1.0"`. The PatronAI dashboard shows a banner when the compliance_map.yaml is older than 90 days: "Compliance mappings may be stale — last reviewed {date}." Forces annual review.

Meera (Engineer): The implementation risk is in the reporter extension. The R6 compliance report is already one of the more complex reports. Adding a compliance annex with control tagging requires changes to data_builder.py, r6_compliance.py, and the reporter/reporter.py orchestration. 2 days is tight if we want it to look good in the PDF output.

Ravi (Founder): Bump to 3 days. Add staleness banner at 90 days. Version the YAML explicitly with framework version numbers. Fatima's 90-day review reminder is a must-have — add it to the settings_form so operators get an in-app nudge.

**Round 1 Verdict:** ✅ Ship it — board-level visibility justifies the effort. ✅ 90-day staleness banner mandatory. ✅ Bump estimate to 3 days. ✅ Framework version in YAML header.

---

**Round 2**

Fatima (Security): I want to push on the EU AI Act mapping specifically. The Act classifies AI systems by risk tier — unacceptable risk, high risk, limited risk, minimal risk. Most of what PatronAI detects (shadow ChatGPT usage, unauthorized API calls) falls into "limited risk" or "minimal risk" under the Act. We'd be misleading a CISO if we tag a ChatGPT finding with "Article 9 — high-risk AI risk management" because ChatGPT is not a high-risk AI system under the Act's definition.

Bruce (CISO): Fatima is right and this is the kind of nuance that could embarrass a CISO in an audit. The compliance mapping needs a risk-tier qualifier. Not just "this finding maps to EU AI Act Article 9" but "this finding maps to EU AI Act Article 9 IF the AI system being used is classified as high-risk."

Seibel (Advisor): For v1, the safest approach is conservative mapping. Only map findings to controls that are clearly triggered regardless of AI risk tier. GDPR Article 22 (automated decision-making) and SOC2 CC6.1 (logical access) apply regardless of risk tier. EU AI Act — mark as "conditional" pending customer's own risk tier classification.

Ravi (Founder): Right call. v1 maps GDPR and SOC2 unconditionally. NIST AI RMF mapped at the "Govern" and "Map" function level — those apply to any AI use. EU AI Act tagged as "conditional — verify risk tier classification" with a link to the Act's Annex III for customer reference. Auditors will appreciate the honesty.

**Round 2 Verdict:** ✅ Conservative mapping for v1 — GDPR and SOC2 unconditional. ✅ NIST AI RMF at function level only. ✅ EU AI Act tagged "conditional" with risk-tier caveat. This is the right thing to do even if it reduces the apparent coverage.

---

## Drama Verdicts Summary

| Gap | Drama Recommendation | Post-Drama Strategy Revision |
|---|---|---|
| Gap 1 — Enforcement | Cloudflare Gateway + immediate-unblock UI. WARP = customer-owned. Enforcement behind settings flag. | **Revised:** Route53 Resolver DNS Firewall (VPC) + hook agent hosts-file (endpoint). No Cloudflare dependency. Unblock-now API call wired to Route53 Resolver. 4 days. |
| Gap 2 — DLP | Cloudflare Worker. Hard dependency on Gap 1. Benchmark CPU. 4 patterns. | **Revised:** Python DLP proxy container in docker-compose (aiohttp). Same 4 patterns from code_engine.py. Depends on Gap 1 enforcement to capture non-proxy traffic. 5 days. |
| Gap 3 — SOAR | PERSONAL_KEY + MCP_CONFIG_CHANGED → auto-execute. S3 action queue. Secrets Manager for creds. | **Revised:** Prism7 (Giggso) via structured email. PatronAI sends JSON email, Prism7 executes playbook in 90s. S3 action queue pattern still applies for revoke. 2 days. |
| Gap 4 — Threat Intel | GreyNoise (7-day cache). Multi-source threshold. GuardDuty import. | **Revised:** AlienVault OTX (free, 10k/day) replaces GreyNoise. MITRE ATLAS added. Multi-source threshold retained. GuardDuty import retained. 3 days. |
| Gap 5 — SIEM | Security Hub ASFF. 4 days. Severity filter. Splunk first. | **Revised:** Deferred to v2. v1: document S3 path for customer SIEM connectors. v2: OpenSearch in docker-compose. 0 days v1. |
| Gap 6 — UEBA | NEW_PROVIDER first. 14-day grace period. Other flags → v2. MaxMind GeoLite2 added. | **Revised:** Log Analyzer (Giggso) via S3. PatronAI writes findings_current/, Log Analyzer writes anomalies/ back. 14-day grace period retained. 3 days. |
| Gap 7 — Compliance | 3 days. 90-day staleness banner. EU AI Act "conditional." GDPR + SOC2 unconditional. | **Unchanged.** 3 days. Same approach. |

---

*Drama session closed — Andie v5.0 — 2026-05-16*  
*Strategy revision applied — 2026-05-17*
