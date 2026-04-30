# Changelog

## [Unreleased]

### Phase 1C — Hourly S3 rollups for chat + data citations + chat-history lifecycle — 2026-04-30

**Problem.** Three failures observed against a real tenant (1098 historical findings on a single device):

1. **The chat answered nonsense.** "Which AI tools does my team use most?" returned generic boilerplate ("the team primarily utilizes tools associated with high-severity findings"). Trace: the 8 chat tools at `dashboard/ui/chat/tools.py` filtered an in-memory `events` list loaded by `dashboard/ui/data.py:load_data()`. That loader walked back 7 days, capped at 500 rows per day, and **returned the first non-empty day and stopped** — so the chat saw at most ~500 rows from a single day. The LFM2.5-1.2B-Thinking model with no real data hallucinated from the tool definitions instead of calling them.
2. **No citations.** Even when the LLM did call a tool, the response had no source attribution — the user couldn't tell whether it pulled real data or made it up.
3. **The CLEAR ✕ on the chat panel only wiped browser session_state.** S3 chat history under `chat/{sha256(email)[:16]}/{view}/YYYY-MM-DD.jsonl` accumulated forever — no lifecycle, no on-press delete.
4. **60-second LLM read timeout** killed multi-step tool-call queries because the Thinking model emits long reasoning traces before each call.

**Fix.**

#### Hourly S3 rollups — chat data backend

- **`src/jobs/hourly_rollup.py`** *(new, 296 LOC)* — `compute_hourly_rollup(window)` runs once an hour at `:05`, S3-Selects the previous hour out of `findings/YYYY/MM/DD/{severity}.jsonl`, groups by `owner` AND by `company`, writes **two parallel trees** of small gzipped dimension files:
  - `s3://{bucket}/users/{sha256(email)[:16]}/rollup/YYYY/MM/DD/HH/by_{provider,severity,device,category}.json` *(per-person — exec view reads from here)*
  - `s3://{bucket}/tenants/{sha256(company)[:16]}/rollup/YYYY/MM/DD/HH/by_{provider,user,severity,device,category}.json` *(team-wide — manager/support/home views read from here)*
  - Plus `_meta.json` per hour with row count, run timing, scope identity.
  - Volume-independent: rollup file size is bounded by dimension cardinality (providers × users × …), not raw event count. 30 days × 24 hours = 720 small files merged at query time.
  - On a fresh deploy with no existing rollups, `catch_up_rollups()` backfills the last `ROLLUP_INITIAL_BACKFILL_DAYS` days (default 7) so chat has historical data from boot.
  - CLI: `python -m src.jobs.hourly_rollup --catch-up | --backfill --start ... --end ... | --hour ...`.
- **`src/normalizer/provider_names.py`** *(new, 144 LOC)* — `normalize_provider(category, raw_provider)` maps raw rows from `agent_explode.py` to human AI-tool names: `claude.ai → "Anthropic Direct"`, `github.copilot → "GitHub Copilot"`, `pip:openai → "OpenAI SDK"`, `chatgpt.com → "OpenAI ChatGPT"`, etc. `unauthorized.csv` takes precedence over the built-in dict for browser-domain mapping (tenant-curated overrides). Unknown raw providers pass through as-is and get logged to `s3://{bucket}/rollup-meta/unknown_providers.jsonl` so the dictionary can grow over time.
- **`src/query/rollup_reader.py`** *(new, 220 LOC)* — `read_dimension_range(scope, scope_id, dim, start, end)` parallel-fetches all hourly rollup files for the window (16-worker thread pool, gzip-decoded), merges per-dimension (set-union for distinct user/device counts), 5-minute in-memory LRU.
- **`main.py`** v1.2.0 — adds `rollup_scheduler` daemon thread alongside the existing scanner / alerter / url_refresh threads. Watchdog auto-restarts container if rollup thread dies.

#### Chat tools rewritten on top of rollups

- **`dashboard/ui/chat/tools.py`** v2.0.0 — every tool is now a thin wrapper around `read_dimension_range`. Signature changed to `(scope, scope_id, **kwargs)`. The legacy `events` arg is dropped from the tool surface entirely; `engine.py` derives `(scope, scope_id)` once per turn from `view + email + company`:
  - `view == "exec"` → `scope="user"`, `scope_id=hash16(email)`
  - `view in {"manager", "support", "home"}` → `scope="tenant"`, `scope_id=hash16(company)`
- **Citation in every tool result.** Each successful tool returns a `_citation` block: `{source: "S3 hourly rollups", scope, scope_id (truncated), window: {start, end}, dimensions, rows_aggregated, s3_path_pattern}`. The system prompt mandates the LLM end every answer with a `**Sources:**` section listing the `s3_path_pattern` from each tool call.
- **`no_data` envelope.** When rollups are empty for the requested scope/window, tools return `{no_data: true, _message, _citation}` so the LLM tells the user honestly instead of fabricating numbers.
- **`dashboard/ui/chat/prompts.py`** v2.0.0 — system prompt mandates tool calls (never describes them in prose), routes specific question patterns to specific tools, requires the **Sources:** footer, instructs honest "no data" responses.
- **`dashboard/ui/chat/tools_schema.py`** v2.0.0 — every tool exposes `days_back` so the LLM can widen/narrow the window.
- **`dashboard/ui/chat/engine.py`** v2.0.0 — dispatch table split into `_SCOPED_TOOLS` (need data context) and `_UNSCOPED_TOOLS` (`get_help`); engine resolves scope once per turn.

#### Chat history lifecycle + Clear confirmation modal

- **`dashboard/ui/chat/history.py`** v1.1.0:
  - `clear_history(email, view)` — `list_objects_v2` + batched `delete_objects` under the user's `chat/{hash16}/{view}/` prefix. Other users' data untouched.
  - `ensure_lifecycle_policy(retention_days=30)` — applies an idempotent S3 lifecycle rule on prefix `chat/`. **Merges** with existing rules — never overwrites them. Called once at startup from `main.py`.
- **`dashboard/ui/chat/widget.py`** v2.2.0 — CLEAR ✕ now opens a `@st.dialog("Clear conversation?")` modal showing the **exact S3 path** that will be deleted (e.g. `s3://patronai/chat/9f5d5df9e012e769/manager/`) with OK / Cancel. OK actually deletes from S3 + queues a toast confirming N files removed.

#### LLM transport — timeout + max tokens

- **`dashboard/ui/chat/llm/openai_compat.py`** v1.3.0 — read timeout `60 → 180s` (env-tunable via `LLM_READ_TIMEOUT_S`); connect timeout split off at 10s so an unreachable server fails fast; `max_tokens=1024` cap (env-tunable via `LLM_MAX_TOKENS`) to prevent runaway thinking-model output.

#### Infra — IAM + env vars

- **`iam-policy.json`** — added `s3:GetBucketLifecycleConfiguration` and `s3:PutBucketLifecycleConfiguration` to the `TenantStorage` statement so `ensure_lifecycle_policy()` can apply on first boot. **Deploy step required: re-attach IAM policy to the existing role.**
- **`docker-compose.yml`** — new env vars (all optional with sane defaults):
  - `ROLLUP_HOURLY_OFFSET_MINUTES=5` — minute past each hour to fire the rollup job.
  - `ROLLUP_INITIAL_BACKFILL_DAYS=7` — first-deploy backfill window.
  - `CHAT_HISTORY_RETENTION_DAYS=30` — lifecycle expiry for `chat/`.
  - `LLM_READ_TIMEOUT_S=180`, `LLM_MAX_TOKENS=1024`.

#### Tests

- **`tests/unit/test_chat_tools.py`** v2.0.0 — 18 tests, all rewritten. Mock `read_dimension_range` (the seam between tools and S3); assert tools shape rollup payloads correctly, citations present, `no_data` envelope returned when rollups are empty, provider names are human-form, severity ranking is correct.

**Result.** 356 unit tests pass. Chat tools no longer require an in-memory event list — they read what they need at query time from per-user / per-tenant rollups in S3. Volume scales without changing the chat path. Every answer carries a citation showing the S3 location. Chat history bounded by both clear-button-deletes-S3 and a 30-day lifecycle.

---

### Phase 1B — RBAC, time format, per-grid search — 2026-04-26

**Problem.** Three rough edges that were making the dashboard "navigation hell" once Phase 1A's data started landing:

1. **Authorisation was env-var only.** `ALLOWED_EMAILS` + `ADMIN_EMAILS` got set at deploy time and required a redeploy to add or change a user. The `Users` settings tab was read-only — display badges + an "edit env vars and restart" hint.
2. **Timestamps shipped raw.** ISO-8601 with microseconds (`2026-04-26T02:33:34.984221+00:00`) on every row. Unreadable at a glance; no timezone awareness.
3. **No global search on grids.** Every table had its own ad-hoc dropdown filters; nothing matched substring across columns. Finding "alice's MCP servers" required scrolling through thousands of rows.

**Fix.**

#### RBAC (S3 users.json)

- **`src/store/users_store.py`** *(new, 142 LOC)* — S3-backed CRUD for `s3://patronai/users/users.json`. Schema per email: `{role: 'exec'|'manager'|'support', is_admin: bool, added_at, added_by}`. First-run migration from `ALLOWED_EMAILS`/`ADMIN_EMAILS` env vars when `users.json` is absent (admins → `manager` + `is_admin=true`; allowlist → `support`). Validates roles + emails; refuses bad input.
- **`dashboard/auth.py`** v2.0.0 + **`dashboard/ui/auth_gate.py`** v2.0.0 — both gates now resolve via UsersStore. Return `(email, role, is_admin)` tuple instead of `(email, is_admin)`. Env-var fallback retained for transient S3 outages so the dashboard never locks itself out.
- **`dashboard/ui/sidebar.py`** v2.0.0 — `_options_for(role, is_admin)` builds the menu per role. Matrix:
  - `exec` → Exec only
  - `manager` → Manager + Provider Lists
  - `support` → Support + Manager (read-only) + Provider Lists
  - `admin` (any base role) → all of the above + Settings; lands on user's role's view
  Replaced the `SUPPORT_EMAILS` env var with the `role` field.
- **`dashboard/ui/tabs/users.py`** v2.0.0 — interactive CRUD UI. Add user form + per-row Edit / Remove buttons + role pill + admin badge. Inline edit form uses a sibling `users_widgets.py` (split for the cap).
- **`dashboard/ui/tabs/users_widgets.py`** *(new, 63 LOC)* — pills + edit form helpers.
- **`dashboard/ghost_dashboard.py`** — destructure 3-tuple from `gate()`; pass `role` through to sidebar.

#### Time format helper

- **`dashboard/ui/time_fmt.py`** *(new, 136 LOC)* — `fmt(iso, tz_name=None)` returns `DD-MMM-YY HH24:MM:SS TZ` (e.g. `26-APR-26 14:30:45 IST`). Auto-detects browser timezone via `st.context.timezone` (Streamlit 1.32+); falls back to session-state override, then UTC. Plus `relative()` ("2m ago" / "3h ago" / "5d ago") and `tooltip()` (raw UTC ISO for `<title>` attributes). Standalone: stdlib `zoneinfo` + Streamlit only.
- **`tests/unit/test_time_fmt.py`** *(new, 17 tests)* — shape, TZ conversion, Z-suffix, naive-ISO, garbage handling, all 12 month abbreviations, relative wording.
- Wired into Risks tab, AI Inventory tab, Asset Map page, Manager → Logs, Support → Signals, header freshness banner.

#### Per-grid search/filter

- **`dashboard/ui/filtered_table.py`** *(new, 142 LOC)* — `filtered_table(df, key, ...)` wraps `st.dataframe` with a global search bar + active-filter chip + result count. `search_box(key)` and `apply_search_dicts(rows, query)` for HTML-rendered tables. Case-insensitive substring match across all string columns; numeric columns ignored.
- **`tests/unit/test_filtered_table.py`** *(new, 9 tests)* — case-insensitive, substring, multi-column, NaN-safe, numeric-ignored.
- Wired into:
  - Manager → Risks (DataFrame; with row selection)
  - Manager → Inventory (HTML table; search above)
  - Manager → AI Inventory (HTML table; search above the existing per-column filters)
  - Manager → Logs (HTML table; search alongside existing dropdowns)
  - Support → Signals (HTML table)
  - Support → Rules (DataFrame; full denylist now searchable instead of capped at first 20 rows)

#### Tests

- **42 new unit tests** added (16 users_store + 17 time_fmt + 9 filtered_table). All passing.
- **0 regressions** to prior 199 tests. **Combined: ~241 polars-free tests + 4 polars-gated.**

#### File-cap discipline

- 3 splits where the cap demanded:
  - `dashboard/ui/tabs/users.py` (165 → 120) → `users_widgets.py` (63)
- All Phase 1B files ≤ 150 LOC.

#### Operator notes

- **No env-var changes required** — first dashboard load auto-migrates from `ALLOWED_EMAILS` / `ADMIN_EMAILS` to S3 `users.json`. Existing access stays exactly the same.
- **Re-deploy via `deploy_to_ec2.sh`** — server + dashboard land on EC2.
- **Browser timezone auto-detected**; users in IST see IST timestamps, users in EST see EST. Tooltip on hover shows raw UTC ISO for audit copy-paste.
- **Open-source friendly** — no SES, no OAuth, no third-party APIs introduced. SMTP / email module is intentionally deferred to V1.1 (see memory).

---

### Phase 1A — MCP / Agent / Tools / Vector-DB inventory + Asset Map — 2026-04-26

**Problem.** The dashboard could see a per-finding row when a known AI tool ran or a known package was installed, but **four entire classes of shadow AI were invisible:**

1. **MCP servers** configured in Claude Desktop / Cursor / Continue / Cline — never scanned.
2. **Autonomous agent workflows** (n8n flows, Flowise flows, langflow YAMLs) sitting on disk waiting to run — never scanned.
3. **Scheduled AI agents** (cron / launchd) — never enumerated.
4. **Local RAG stores** (Chroma, FAISS, LanceDB, Qdrant, Milvus, DuckDB-vector) — never inventoried.

Plus there was no per-user view: the dashboard showed events but not "what AI does Alice have on her laptops" in one place.

**Fix.**

- **`agent/install/scan_redactor.py.frag`** *(new, 78 LOC)* — shared util. Strips API keys / JWTs / generic tokens; replaces `/Users/giggso/...` with `~/...`. Every Phase 1A finding passes through `_safe_finding()` then `_has_unredacted_secret()` — if a secret survived redaction, the finding is dropped entirely (never partially uploaded).
- **`agent/install/scan_repo_discovery.py.frag`** *(new, 116 LOC)* — auto-walks `$HOME` for `.git/` directories. No hardcoded paths. Honours exclusions (`node_modules`, `.venv`, `Library`, etc.), 6-level depth cap, 60 s time cap. Exposes `DISCOVERED_REPOS` global to downstream scanners so they don't trawl the home dir.
- **`agent/install/scan_first_run.py.frag`** *(new, 42 LOC)* — reads `~/.patronai/first_run.flag`. Exposes `IS_FIRST_RUN` for downstream scanners. Footer clears the flag after a successful payload print.
- **`agent/install/scan_mcp_configs.py.frag`** *(new, 127 LOC)* — reads the four known MCP config JSONs. Emits one `mcp_server` finding per server with redacted metadata: server name, command basename only, `arg_flags` (no values), `env_keys_present` (no values), `transport`, and a SHA-256 of the parent file for change detection.
- **`agent/install/scan_agents_workflows.py.frag`** *(new, 144 LOC)* — finds `n8n` workflow JSONs, Flowise flow JSONs, langflow YAMLs; parses `crontab -l` for AI-keyword entries; reads `~/Library/LaunchAgents/*.plist` for AI references. Emits `agent_workflow` + `agent_scheduled` findings.
- **`agent/install/scan_tools_code.py.frag`** *(new, 114 LOC)* — greps Python files inside `DISCOVERED_REPOS` for `@tool`, `@function_tool`, `Tool(...)`, `register_tool(...)`, framework tool registries. **Counts only — never ships source lines.** Time-capped at 30 s. Emits `tool_registration` findings.
- **`agent/install/scan_vector_dbs.py.frag`** *(new, 134 LOC)* — finds `chroma.sqlite3`, `*.faiss`, `*.lance`, `*.duckdb` files; Qdrant / Milvus signature files; vector dirs (`.chroma`, `lancedb`, `qdrant`, `weaviate`). Two passes: home caches + inside discovered repos. Emits `vector_db` findings.
- **`agent/install/setup_agent.sh.template` + `.ps1.template`** — wire the 7 new fragments via `scan_fragment_loader.py`'s updated `FRAGMENT_ORDER`. Drop `~/.patronai/first_run.flag` at install time. No hot-update path; existing fleet needs re-install for Phase 1A visibility.
- **`agent/install/scan_footer.py.frag`** v2.0.0 — calls 4 new emitters; tags every payload with `scan_kind` (`baseline` first run, `recurring` after); emits `repos_discovered` summary array; clears the first-run flag after success.

#### Server-side

- **`src/normalizer/schema.py`** v2.0.0 — added 12 optional fields (`mcp_host`, `config_sha256`, `server_name`, `command_basename`, `arg_flags`, `env_keys_present`, `transport`, `framework`, `schedule_expr`, `kind`, `scan_kind`, `scan_id`). Backwards-compatible — every new field has a safe default; legacy events still serialize.
- **`src/normalizer/agent_explode.py`** v1.1.0 — added 4 new categories to `_FINDING_SEVERITY` (HIGH for mcp_server / agent_workflow / agent_scheduled, MEDIUM for tool_registration / vector_db); extended `_provider_for()` with category-aware label generators.
- **`src/normalizer/agent_explode_fields.py`** *(new, 44 LOC; split from agent_explode.py to honour the 150-LOC cap)* — Phase 1A field-promotion whitelist. Copies `mcp_host`, `server_name`, `kind`, etc. from finding onto event so the dashboard reads them as top-level columns instead of parsing the `notes` blob.
- **`src/ingestor/pipeline.py`** v2.1.0 — after writing each `mcp_server` finding, calls `maybe_emit_mcp_change`. If `config_sha256` differs from the last-known hash for `(device, mcp_host)`, emits a derived `mcp_config_changed` HIGH-severity event for the alerter.
- **`src/ingestor/pipeline_mcp_change.py`** *(new, 55 LOC; split from pipeline.py)* — the hash-flip detection logic.
- **`src/store/findings_query.py`** *(new, 97 LOC)* — `last_known_mcp_hash`, `record_mcp_hash`, `read_by_email`, `read_by_repo`. Free functions over s3 client; easier to test, easier for the dashboard to reuse without circular imports. MCP hashes persisted at `s3://patronai/mcp_hashes/{device}/{host}.txt`.

#### Dashboard

- **`dashboard/ui/manager_tab_ai_inventory.py`** *(new, 105 LOC)* — Manager view's 5th tab. KPIs (MCP servers / workflows / scheduled / tool repos / vector DBs), filter row (severity, category, owner, search), deduped table — one row per `(owner, device, category, provider)` showing LATEST observation. Owner cells link to the Asset Map.
- **`dashboard/ui/manager_tab_ai_inventory_data.py`** *(new, 93 LOC; split for cap)* — pure-data helpers (filter / dedup / KPI counts / owner enumeration). Streamlit-free; easy to unit-test.
- **`dashboard/ui/asset_map.py`** *(new, 143 LOC)* — per-user AI ASSET MAP page. Plotly Treemap (User → Repo → Category → Asset) plus nested expander tree. Reached via `?view=asset_map&email=…` query param.
- **`dashboard/ui/asset_map_route.py`** *(new, 31 LOC)* — query-param router. Lifted from `ghost_dashboard.py` to keep that entry under the cap.
- **`dashboard/ui/header.py`** *(new, 56 LOC)* — three-column header strip extracted from `ghost_dashboard.py` so the entry stays under 150 LOC for the first time.
- **`dashboard/ui/manager_view.py`** v1.1.0 — added 5th tab `AI INVENTORY`.
- **`dashboard/ghost_dashboard.py`** — added Phase 1A query-param routing; previously over the 150-LOC cap, now under via two splits.

#### Tests

- **`tests/unit/test_secret_redactor.py`** *(new, 10 tests)* — covers OpenAI / Anthropic / AWS / JWT / home-path redaction + the unredacted-secret guard.
- **`tests/unit/test_mcp_config_scan.py`** *(new, 7 tests)* — empty-config / one-server / arg-values-dropped / env-values-dropped / hash-flip / invalid-JSON-skipped.
- **`tests/unit/test_agents_workflows_scan.py`** *(new, 7 tests)* — n8n / Flowise / langflow detection + skip-non-workflow + filename cap.
- **`tests/unit/test_tools_code_scan.py`** *(new, 9 tests)* — `@tool` / `@function_tool` detection + node_modules / .venv exclusion + multi-decorator counting + safe paths.
- **`tests/unit/test_vector_dbs_scan.py`** *(new, 9 tests)* — chroma.sqlite3 / .faiss / .lance detection in home caches + repos; vendor-dir exclusion; path redaction.
- **`tests/unit/test_agent_explode_phase1a.py`** *(new, 16 tests)* — severity tiers + provider strings + Phase 1A field promotion + scan_kind passthrough.
- **`tests/unit/test_pipeline_mcp_change.py`** *(new, 6 tests)* — non-MCP / first-sighting / unchanged / flipped / missing-fields / provider-tag.
- **`tests/unit/test_findings_query.py`** *(new, 10 tests)* — MCP hash get/put round-trip + key sanitisation + read_by_email / read_by_repo (polars-gated for environments without the binary).
- **`tests/unit/test_ai_inventory_data.py`** *(new, 15 tests)* — dashboard data helpers (filter / dedup / KPI / owner enumeration).
- **`tests/unit/test_endpoint_scan_paths.py`** — extended `EXPECTED_FUNCTIONS` with the four new emitters.
- **`tests/unit/test_heartbeat.py`** + **`test_render_agent_package.py`** — pre-existing failures fixed (stale assumptions; not Phase 1A regressions).

#### Cleanup discipline

- **`codecleanup.md`** *(new)* — index of `CLEANUP-PHASE-*` sentinels for the eventual OSS razor pass.
- **`scripts/strip_cleanup_blocks.sh`** *(new, 95 LOC, executable)* — pre-OSS-launch razor. Greps `CLEANUP-PHASE-*` sentinels, strips both sentinels and the lines between, deletes whole-file removals listed in `codecleanup.md`, then deletes the MD and itself. Idempotent; dry-run by default; `--final` to actually act.
- **Per-phase tag** — Phase 1A uses tag `CLEANUP-PHASE-1A`. Phase 1A is purely additive — zero sentinels needed today.

#### File-cap discipline

Strict 150 LOC cap honoured. Splits where the cap demanded:

- `agent_explode.py` ~159 LOC → split out `agent_explode_fields.py`
- `pipeline.py` ~153 LOC → split out `pipeline_mcp_change.py`
- `findings_store.py` near cap → new helpers in sibling `findings_query.py`
- `manager_tab_ai_inventory.py` ~165 LOC → split out `manager_tab_ai_inventory_data.py`
- `ghost_dashboard.py` 165 LOC pre-existing → split out `header.py` + `asset_map_route.py`; first time under cap

#### Operator notes

- **Re-install required on existing Macs** — Phase 1A bakes 7 new fragments into `setup_agent.sh.template`. Old laptops keep working but won't see new findings until re-installed.
- **First scan after re-install runs in baseline mode** (deeper exclusions, broader walk). Subsequent 30-min scans run in lighter recurring mode.
- **MCP config-change alerts** fire on the first observed hash flip per `(device, mcp_host)`. First sighting itself is silent (no last hash to compare against).
- **Privacy gate** — secrets matched after redaction cause the entire finding to drop with a debug-log entry. Better to lose visibility than to leak.
- **Open-source posture** — detection regexes live in fragments where extending them is a pure-code change; depth/time caps are tunable via `config/repo_discovery.yaml`. No customer-specific values; only Giggso author headers per CLAUDE.md ground rules.

---

### Step 0.5 — Server-side data flow + per-finding events — 2026-04-26

**Problem.** Live agent telemetry was reaching S3 (HTTP 200 in `agent.log`) but the dashboard stayed empty. Two stacked server-side bugs:

1. **Cursor walked past `latest.json` and never returned.** `s3_walker.list_new_files()` used `StartAfter=after_key` against an alphabetical S3 listing. Once the cursor advanced past `ocsf/agent/scans/{token}/latest.json`, the same overwritten file was never re-read. Heartbeats and scans that the laptop kept refreshing every 5 / 30 min were ingested exactly once.

2. **ENDPOINT_SCAN dropped at the dst-domain check.** `pipeline.process()` filtered out events without `dst_domain` or `dst_port`. ENDPOINT_SCAN carries a *list* of findings, not a single network destination — so even on the one cycle a scan was read, the whole event was discarded silently.

**Fix.**

- **`src/ingestor/s3_walker.py`** v2.0.0 — cursor switched from key (`StartAfter=`) to **LastModified timestamp** (`obj.LastModified > after_ts`). Same key gets re-yielded each cycle when the laptop overwrites it. Returns `[(key, last_modified)]` tuples; ingestor advances on `max(last_modified)`.
- **`src/store/cursor_store.py`** v2.0.0 — adds `cursor_ts` field. Legacy v1 cursors auto-migrate: `cursor_ts = last_processed_at - 1 h`, so the dashboard back-fills the most recent hour of data on first cycle after upgrade. No manual reset.
- **`src/ingestor/ingestor.py`** v2.0.0 — feeds timestamp cursor to the walker; tracks max LastModified across the cycle; persists via the new `cursor_store.write(cursor_ts=…)`.
- **`src/ingestor/pipeline.py`** v2.0.0 — pre-routes `event_type == "ENDPOINT_SCAN"` to a new `_process_endpoint_scan()` method that explodes each finding into one flat event and writes it directly. Skips the matcher (agent already classified) and never trips the dst-domain filter.
- **`src/normalizer/agent.py`** v1.4.0 — exposes `explode_endpoint_findings(raw, company)` returning `List[dict]`.
- **`src/normalizer/agent_explode.py`** *(new, 101 LOC)* — the actual explosion logic. Severity tier per finding type (HIGH for browser/process/container_log_signal; MEDIUM for package/ide_plugin/container_image; LOW for shell_history). Each event tagged with `scan_id = "{token}-{timestamp}"` so all findings from the same scan can be grouped back. Type-specific fields land in distinctive slots: browser → `dst_domain`, others → `process_name`. `provider` set per finding for dedup keying.

#### Clean-scan policy

A scan with zero findings now drops entirely — heartbeat (5 min) covers liveness; we don't bloat storage with "scan ran fine" rows. Operator-locked policy: see `project_email_ses_fix_deferred.md` predecessor session.

#### Alerter — generic, no change needed

`alerter._process_one()` reads `severity` and `provider` from any event; doesn't care whether the source was network telemetry or ENDPOINT_FINDING. New events flow through the existing dedup → SNS → Trinity webhook → SES email pipeline automatically. HIGH/CRITICAL ENDPOINT_FINDINGs page on-call; MEDIUM/LOW land on the dashboard only.

#### Tests
- **`tests/unit/test_endpoint_scan_flow.py`** *(new, 12 tests)* — clean-scan-drop, N-findings-explode-to-N-events, severity tiers, identity propagation, scan_id grouping, notes blob audit shape.
- **`tests/unit/test_cursor_migration.py`** *(new, 7 tests)* — first-run defaults, corrupt-cursor reset, v1 → v2 migration with -1 h seed, v2 pass-through, write contract.
- **98 / 98 unit tests passing** across rule_model + messy + code_analyser + scan_paths + csv_validity + identity_binding + endpoint_scan_flow + cursor_migration.

#### Operator notes
- **No agent rebuild needed** — fix is server-side. Existing fleet keeps working as-is.
- **Deploy + restart** the EC2 container; the cursor migrates automatically on first read; data starts populating dashboard within 5 min.
- **What you'll see**: heartbeats today climbing every 5 min; finding rows accumulating in `ocsf/findings/YYYY/MM/DD/`; manager dashboard inventory, exec view, and discovered AI tools panel all back-filling.
- **Alerter fires** on first HIGH ENDPOINT_FINDING per (device, provider) per dedup window; clean-scan drop means no email noise on idle laptops.

---

### Step 0.1 — Auto-coverage for new repos — 2026-04-25

**Problem.** Today the installer walks `$HOME` once at install time and symlinks the pre-commit hook into every existing repo. Anything cloned or `git init`-ed afterwards never gets the hook — fleet coverage decays to zero over a few months as devs work in new repos.

**Two-layer fix.**

1. **Git template directory** — at install, the agent sets `init.templateDir = ~/.patronai/git-template/` (with our pre-commit symlink inside). Git copies this into every new `.git/` on `init` *or* `clone`. Native git mechanism; no scanning at runtime.
2. **Periodic backstop** — every heartbeat (5 min), the agent walks `$HOME` (depth 6) and ensures every `.git/hooks/pre-commit` is our symlink. Catches repos cloned before the agent was installed and any rare miss by the template path. Logs `{type:"hook_backstop","added":N}` to `agent.log` when it adds.

**Files**
- **`agent/install/setup_agent.sh.template`** — template-dir install + heartbeat backstop. Honours an existing `init.templateDir` (drops our hook into theirs additively, leaves the rest alone).
- **`agent/install/setup_agent.ps1.template`** — Windows parity.
- **`agent/install/uninstall_agent.sh`** — clears `init.templateDir` if it points at us; removes our hook from a foreign template dir without disturbing the rest; then deletes `~/.patronai/`.

**Edge cases handled**
- Pre-existing customer `init.templateDir` (e.g. for Husky / lefthook bootstraps) — additive merge, never overwritten.
- Project hooks (Husky, lefthook) — same `.backup` logic as the install-time pass.
- Reinstall idempotency — re-running setup is a no-op when `init.templateDir` already points at us.

**Operator notes**
- Re-issue installers via Deploy Agents tab so existing fleet picks up Step 0.1.
- After install, `git init` and `git clone` automatically get the hook — no `~/.patronai/install_hook.sh /path/to/repo` ceremony for end users.

---

### Step 0 — Endpoint data flow + identity binding — 2026-04-25

**Problem:** deployed installers stopped reaching S3. Root causes — heartbeats wrote outside the ingestor's walked prefix; heartbeats overwrote the install report; presigned write URLs expired silently after 7 days; failures were swallowed by `|| true`; no MAC / IP / email captured for unique row binding.

#### S3 routing — fixed
- **`src/store/agent_store.py`** v2.0.0 — `get_presigned_urls()` rewritten. Heartbeat now signs `ocsf/agent/heartbeats/{token}/latest.json` (inside the ingestor's walked prefix). Scans stay at `ocsf/agent/scans/{token}/latest.json`. Status (install report) stays at `config/HOOK_AGENTS/{token}/status.json` and is no longer clobbered every 5 minutes. New helper `_sign_get` / `_sign_put` collapses the duplicated minting code.

#### Refreshable presigned URLs (the 7-day cliff)
- **`src/agent_url_refresh.py`** *(new, ~80 LOC)* — `refresh_all_tokens(store)` walks the agent catalog and re-mints fresh URL bundles per token. `url_refresh_loop()` is a daemon target that wakes daily. Never raises — one bad token can't kill the loop.
- **`src/store/agent_store.py`** — `write_url_bundle(token, os_type)` writes `config/HOOK_AGENTS/{token}/urls.json` carrying current `heartbeat_put_url` / `scan_put_url` / `authorized_get_url` (each minted at 7-day TTL). `get_presigned_urls()` returns one extra URL — `urls_refresh_url`, a presigned GET on the bundle.
- **`src/blob_index_store.py`** — wires `AgentStore` so `store.agent` is reachable from the daemon thread.
- **`src/threads.py`** + **`main.py`** — fourth daemon thread `url_refresh_loop` alongside scanner / alerter / streamlit. Re-mints daily, 6+ days of headroom.
- **Agent side**: every heartbeat (5 min) GETs `urls.json` and overwrites local `heartbeat_url` / `scan_url` / `authorized_url`. The 7-day cliff that was silently killing fleet agents is gone.

#### Identity binding (token + email + device_uuid + mac_primary + ip_set)
- **`agent/install/scan_header.py.frag`** v1.1.0 — captures `EMAIL`, `DEVICE_UUID`, `MAC_PRIMARY` from `~/.patronai/config.json` (baked at install) and `IP_SET` fresh each cycle via stdlib `socket`.
- **`agent/install/scan_footer.py.frag`** — every ENDPOINT_SCAN payload now carries the identity bundle.
- **`agent/install/setup_agent.sh.template`** + **`setup_agent.ps1.template`** — `config.json` writes `email`, `device_uuid` (`uuid.uuid4()` once at install), `mac_primary` (from `uuid.getnode()` / `Get-NetAdapter`). Heartbeat scripts emit the same identity bundle and refresh URLs each cycle.
- **`scripts/render_agent_package.py`** v1.6.0 — passes `RECIPIENT_EMAIL` and `URLS_REFRESH_URL` into the render context for both passes; seeds the first `urls.json` bundle so the laptop has refreshable URLs from minute 0.
- **`src/normalizer/agent.py`** v1.3.0 — new `_bind_identity()` helper propagates email / device_uuid / mac_primary / ip_set onto every flat event. `owner` field now defaults to email (was hostname). Severity tiering for ENDPOINT_SCAN extended to cover `container_log_signal` (HIGH), `ide_plugin` / `container_image` (MEDIUM), `shell_history` (LOW).

#### Local diagnostics (replaces silent failures)
- **`agent/install/diagnose.sh`** *(new)* — recipient runs `bash ~/.patronai/diagnose.sh`. Prints config, current IPs, URL-file presence, last 20 `agent.log` lines, and a live PUT probe with HTTP-status-aware diagnosis (403 → URL expired, 0 → network blocked, 2xx → healthy).
- **`agent/install/diagnose.ps1`** *(new)* — Windows parity.
- Heartbeat / scan wrappers now write a JSON line per PUT to `~/.patronai/agent.log` — `{ts, type, http_status}`. Replaces the silent `|| true` swallowing pattern.
- Both diagnose scripts are rendered into the installer at build time via two new placeholders (`INLINE_DIAGNOSE_SH`, `INLINE_DIAGNOSE_PS1`) — single-source-of-truth, no duplication.

#### Tests
- **`tests/unit/test_identity_binding.py`** *(new, 9 tests)* — locks the contract: HEARTBEAT and ENDPOINT_SCAN both propagate email / device_uuid / mac_primary / ip_set; severity tiering verified; src_ip falls back to hostname when IPs empty; owner falls back to hostname when email missing.
- **79 / 79 unit tests passing** across rule_model + messy CSV + code_analyser + scan paths + CSV validity + identity binding.

#### Operator notes
- **Existing fleet must be re-issued.** Agents installed before Step 0 don't carry the URL refresh code or the identity bundle; they will keep working only until their original 7-day URLs expire. Plan a one-time re-issue via Deploy Agents tab.
- **Bucket config (operator decision, not agent-side)**: enable S3 versioning on the tenant bucket so the per-cycle `latest.json` overwrites carry full history; configure SSE-KMS with a customer-managed CMK if your security team wants per-customer key control.
- **`STRICT_MIN_RULES` unchanged** — still 50.

---

### Group 2 — Coverage expansion + sustainable curation on-ramp — 2026-04-25

#### 2.A — Baseline deny-list expansion
- **`config/unauthorized.csv`** v1.1.0 — net-new SaaS domain rows: Flowise (3), BuildShip (2), Lovable (2), Bolt (1), V0 (2), Stack-AI (2), Cursor SaaS (2), NotebookLM (1), Manus (2), Pika (1), Suno (2). All `HIGH` per default-deny philosophy. Customers can downgrade locally via `unauthorized_custom.csv`.
- **`config/unauthorized_code.csv`** v1.1.0 — IDE plugin IDs for VS Code (Copilot, Copilot Chat, Codeium, Tabnine, Continue, Amazon Q) and JetBrains (Copilot, Codeium, Tabnine). New `type=ide_plugin`.

#### 2.B — Multi-browser path expansion
Endpoint scan now covers **Safari, Chrome, Firefox, Edge, Brave, Arc, Opera, Vivaldi, Chromium** across **macOS, Linux, Windows**. Previously: macOS-only paths regardless of host OS.

#### 2.C — IDE plugin enumeration
Walks every VS Code-family extensions root (`.vscode`, `.vscode-insiders`, `.cursor`, `.vscode-server`) and every JetBrains plugin subdirectory (IntelliJ, PyCharm, GoLand, WebStorm, RubyMine, etc). Matches against the IDE-plugin denylist.

#### 2.D — Container scan (no `docker exec`)
- **L1 — image-name match.** `docker ps -a --format ...` enumerates running AND stopped containers; image regex flags `flowiseai/flowise`, `n8nio/n8n`, `langflow`, `dify`, `ollama`, etc.
- **L2 — log scan.** `docker logs --tail 500` per container; regex catches API endpoints, key prefixes, "loading model" / "prompt_tokens" / "ChatCompletion" telemetry strings.
- **L3 — shell history.** `~/.bash_history`, `~/.zsh_history`, fish history, Windows PowerShell `ConsoleHost_history.txt` — closes the *"pulled an AI image, ran it, deleted it, removed the image"* blind spot. Catches `docker pull/run/build/exec`, `pip install`, `npm install`, `brew install` against AI-related arguments.

#### Template fragment refactor (CLAUDE.md cleanliness)
Endpoint scan logic moved out of the monolithic installer templates into 8 cross-platform `agent/install/scan_*.py.frag` files (header, packages, processes, browsers, ide_plugins, containers, shell_history, footer) — one set serves both bash and PowerShell installers. **`scripts/scan_fragment_loader.py`** (new, 43 LOC) defines `FRAGMENT_ORDER` and `load_scan_fragments()`. **`scripts/render_agent_package.py`** v1.5.0 calls the loader; `agent_renderer` substitutes the concatenated Python into the new `{{INLINE_SCAN_PYTHON}}` placeholder in both templates. Templates dropped from ~370 LOC each to ~250 LOC. **`agent/install/WHY_FRAGMENTS_AND_WHERE.md`** (new) documents the architecture, contracts, and how to add a new scan surface.

#### Sustainable curation — slim L2 review queue
- **`dashboard/ui/tabs/discovered_panel.py`** (new, 150 LOC) — *Discovered AI tools — review queue* section appended to the Provider Lists tab. Aggregates the last 7 days of OCSF `UNKNOWN`-verdict findings, ranks by event count, and lets admins one-click **Promote to deny** (appends to `unauthorized_custom.csv` with audit log) or **Dismiss** (persisted to `config/discovered_dismissed.txt`). No Gemma classifier yet — pure aggregation. Closes the manual-curation treadmill problem the team flagged: novel AI tools that real users hit get surfaced for triage instead of waiting for Giggso to read TechCrunch.
- **`dashboard/ui/tabs/provider_lists.py`** v2.2.0 — wires the discovered panel into the tab.

#### Tests
- **`tests/unit/test_endpoint_scan_paths.py`** (new) — 9 static checks: every fragment exists, concatenated Python parses, footer calls every scan function, summary counts every emitted type, OS branches present in browsers + IDE plugin matrices, no fragment uses `os.uname()`, header reads token from env, every fragment ≤ 150 LOC.
- **`tests/unit/test_rule_csv_validity.py`** (new) — 4 invariants: every shipped CSV passes its real validator, baseline deny ≥ 50 valid rows, IDE plugin patterns present, visual-builder domains present.
- **70 / 70 unit tests passing** (32 rule_model + 11 messy + 10 code_analyser + 9 scan paths + 4 CSV validity + 4 ad-hoc).

#### Operator notes
- **No fleet auto-rerender.** New scan surfaces apply only to **freshly rendered** installers. Existing recipients keep working but won't pick up new browsers / IDE plugins / container scan / shell history until re-issued (locked Group 2 decision).
- **No `docker exec`, no journalctl.** L1+L2 cover most cases; shell history closes the ephemeral-pulled-and-removed gap. Journal scan deferred to V2.
- **Shell history can miss** if `history -c` is used or `HISTFILE=/dev/null` is set. Documented as a known V1 limitation.
- **Fragment refactor is invisible to recipients** — same single-file installer, same JSON payload shape, more findings. Backwards-compatible.

---

### Classifier swap — Gemma 4 E4B → Qwen 3 1.7B — 2026-04-25

The Marauder Scan layer-3 classifier (called only for AMBIGUOUS code-engine triage results) is now Qwen 3 1.7B Q4_K_M instead of Gemma 4 E4B. Same llama.cpp subprocess, same JSON output contract — every caller sees an identical dict shape.

#### Why
- **Apache 2.0 license** — clean for OSS distribution.
- **~3× smaller image footprint** — ~1 GB vs ~3 GB at Q4_K_M quant.
- **~2× faster inference** — typical AMBIGUOUS classification ~500 ms vs ~1.2 s on the same EC2.
- **Native function-calling training** — Qwen 3 was purpose-trained for structured-output tasks; expect higher JSON-mode reliability and fewer fallbacks to `regex_fallback()`.
- **Hybrid thinking mode available** — kept OFF for AMBIGUOUS for snappy classification; reserved for future L2 domain auto-discovery.

#### Files
- **`Dockerfile`** — `INCLUDE_GEMMA` → `INCLUDE_CLASSIFIER`. New args `QWEN_GGUF_REPO=Qwen/Qwen3-1.7B-GGUF` and `LLAMA_CPP_TAG=b4404` for deterministic builds. llama.cpp clone now pinned to a release tag rather than HEAD.
- **`src/code_analyser.py`** v3.0.0 — `MODEL_PATH` default → `/models/qwen3-1.7b-q4_k_m.gguf`; new env `CODE_ANALYSER_NAME` (default `qwen3-1.7b`) stamped on every result; `MAX_TOKENS` 300 → 250 (Qwen tokenizer is more efficient). Same JSON contract; callers unchanged.
- **`tests/unit/test_code_analyser.py`** v2.0.0 — 10 tests, fully rewritten for the Qwen3 + regex-fallback contract. Asserts `_model == "qwen3-1.7b"` on the classifier path and `_model == "regex-fallback"` + `_fallback == <reason>` on every failure path. Includes a regex-risk-level assertion (e.g. `import langchain` → `HIGH`) to confirm the fallback produces useful verdicts.
- **`README.md`** — env-var table refreshed; `INCLUDE_CLASSIFIER`, `QWEN_GGUF_REPO`, `LLAMA_CPP_TAG`, `CODE_ANALYSER_MODEL`, `CODE_ANALYSER_NAME` all documented.

#### Verification
- 53 / 53 unit tests pass (32 rule_model + 11 messy + 10 code_analyser).
- Backwards compat: `code_analyser.analyse()` signature unchanged; `regex_fallback()` from Group 6.7 unchanged; alerter pipeline untouched.

#### Operator notes
- **Build**: `docker build --build-arg INCLUDE_CLASSIFIER=1 -t patronai .` to bake the model in. Default builds skip the bake and rely on `regex_fallback()` — system stays fully functional either way.
- **Pin discipline**: `LLAMA_CPP_TAG=b4404` is a known-good llama.cpp release with Qwen 3 architecture support. Bump only after verifying.
- **HF repo fallback**: if `Qwen/Qwen3-1.7B-GGUF` is unavailable at build time, set `--build-arg QWEN_GGUF_REPO=bartowski/Qwen3-1.7B-GGUF` (or any community quantizer) and rebuild. Same Q4_K_M expected.

---

### Group 6.5 — Bulk-import on-ramp for custom deny lists — 2026-04-25

#### New: drop a CSV, get a clean editable table
- **`dashboard/ui/tabs/provider_lists_import.py`** (new, 100 LOC) — `📥 Bulk import from CSV` expander above each custom deny editor. `st.file_uploader` reads the CSV (BOM-tolerant), runs it through the same `parse_csv_text` + `validate_rule` pipeline as a manual save, and surfaces a metrics card (`✓ valid · ⚠ skipped`) plus an issues table with a `Download issues CSV` button. A single button — `Load N valid rows into editor` — appends cleaned rows into the editor's session-state cache, deduped on key columns (imported wins on collision).

#### Editor enhancements
- **`dashboard/ui/tabs/provider_lists.py`** v2.1.0 — wires the bulk-import widget, adds a `🗑 Clear editor` button next to Save (resets cache + reruns), and a display-only `🔎 Find` text input that highlights matching rows in a read-only dataframe above the editor (does not change the editor).
- **`dashboard/ui/tabs/provider_lists_io.py`** v1.1.0 — session-state cache keyed by S3 path. First render fetches; subsequent renders read from cache. Save refreshes the cache to the saved value. New `clear_cache(key, cols)` helper.

#### Tests
- **`tests/unit/test_rule_model_messy.py`** (new, 113 LOC) — 11 fixtures covering BOM, smart quotes, scheme+path stripping, mixed case, trailing dots, zero-width chars, blank lines, comment lines, severity casing/typos, too-broad rejection, port-out-of-range, partial-failure (one bad row doesn't doom the batch). 43 / 43 unit tests now passing.

#### Docs
- **`README.md`** — Editing flow rewritten with the bulk-import path, the find filter, and the clear-editor semantics.
- **`UserGuide.html`** — new sub-step 5.5.1 *Bulk-upload a CSV* under section 5.5.

---

### Group 6 — Ruleset & Classifier Hardening — 2026-04-25

#### Architecture: forgive-input, store-strict
Admins paste anything; UI normalises and validates before write. Loader treats storage as already clean. No quarantine files, no admin housekeeping. Validation is the same code at write-time and read-time.

#### Custom denylist support — survives Docker rebuilds
- **`config/unauthorized_custom.csv`** (new, empty seed) — customer additions to the network deny list. Edited via Provider Lists tab. Merged with the Giggso-managed baseline at scan time. On `(domain, port)` collision, custom rows win, letting customers locally tighten severity.
- **`config/unauthorized_code_custom.csv`** (new, empty seed) — same pattern for the Marauder Scan code-deny list. On `pattern` collision, custom wins.
- **`src/bootstrap.py`** v1.2.0 — `seed_config_files()` pushes empty seeds only-if-absent. Customer edits never overwritten.

#### Single-source rule model
- **`src/matcher/rule_model.py`** (new, 150 LOC, stdlib only) — `Rule`, `AllowRule`, `CodeRule` validators + normalisers. `normalize_domain()` strips schemes/paths/quotes/zero-width chars/whitespace, lowercases, drops trailing dot. `normalize_severity()` enforces HIGH/MEDIUM/LOW. `is_too_broad()` blocks `*`, `*.com`, `*.org` etc. `valid_glob()` dry-runs fnmatch. `parse_csv_text()` is the boundary function — same code path at UI save and scanner load. `dedupe()` is last-write-wins. `find_conflicts()` pairs allow-list patterns that would suppress a deny rule.
- **`src/matcher/loader.py`** v2.0.0 — uses `rule_model`. Loads baseline + custom; dedupes; returns `(rows, report)` via new `load_unauthorized_full()` / `load_authorized_full()`. Backward-compatible signatures preserved.
- **`src/matcher/code_loader.py`** (new, 86 LOC) — extracted from `code_engine.py`. Same merge logic for code lists.
- **`src/matcher/code_engine.py`** v2.0.0 — triage logic only; loaders re-exported from `code_loader.py`.

#### Strict-mode boot + self-alert
- **`src/rule_health.py`** (new, 114 LOC) — `self_check_rules()` runs after `seed_config_files()` in `main.py`. Loads all four CSV lists, writes `config/load_status.json` for the UI banner, and emits a CRITICAL `degraded_ruleset` finding to S3 if merged deny count is below `STRICT_MIN_RULES` (env, default 50). **Does not exit the process** — degrades gracefully so admins can fix from the UI.
- **`main.py`** — calls `self_check_rules()` after seed.

#### Provider Lists tab — full editing UX
- **`dashboard/ui/tabs/provider_lists.py`** v2.0.0 — orchestration only. Status banner if degraded. Baseline read-only (collapsed expander). Two new editable sections: **Network denylist — Custom additions** and **Code denylist — Custom additions**, both with conflict gates, inline error tables, and Save-anyway override. Allow-list editor migrated to the same validate-on-save flow.
- **`dashboard/ui/tabs/provider_lists_io.py`** (new, 93 LOC) — S3 IO + dataframe helpers. Banner, read-only render, validated read, audit-tracked CSV write.
- **`dashboard/ui/audit_tail.py`** (new, 84 LOC) — *Last 5 changes* expander at the bottom of Provider Lists. Reuses the existing `ocsf/audit/` prefix written by `ui/audit.py`. No new infra.

#### Gemma classifier resilience (Group 6.7)
- **`src/code_fallback.py`** (new, 67 LOC) — `regex_fallback()` produces a Gemma-shaped classification dict from regex patterns over the snippet (frameworks, MCP, hardcoded keys, endpoints, local inference). Risk level inferred from the strongest signal.
- **`src/code_analyser.py`** v2.0.0 — calls `regex_fallback()` on `model_not_found`, `llama_cli_not_found`, `timeout`, `json_parse_failed` instead of returning a stub error dict. Layer 3 of Marauder Scan stays useful when Gemma is unreachable.
- **`Dockerfile`** — `INCLUDE_GEMMA` build arg (default `0`). Set to `1` to bake the GGUF into the image (~3 GB). Default builds stay lean; runtime mounts or S3 download still work; regex fallback covers all paths.

#### Tests
- **`tests/unit/test_rule_model.py`** (new) — 32 pure-data tests covering normalise, validate, parse_csv_text aggregation, dedupe last-write-wins, find_conflicts. No AWS, no LocalStack required.

#### Settings precedence
- New env var `STRICT_MIN_RULES` (default `50`). Self-check warns and self-alerts when merged deny count is below this number.

---

### Agent Endpoint Scan + Per-User Whitelist — 2026-04-20

#### New: Endpoint scan agent
- **`agent/install/setup_agent.sh.template`** — writes `~/.patronai/scan.sh` at install time. Runs every 30 min (launchd on Mac, crontab on Linux). Scans: `pip3 list` / `npm list -g` / `brew list` (AI packages), `ps aux` (running AI processes: n8n, Ollama, Cursor, LM Studio, etc.), Safari + Chrome + Firefox browser history (SQLite, last 7 days, matched against unauthorised domain list). Uploads findings to S3 as `ENDPOINT_SCAN` OCSF event via presigned PUT. First scan fires immediately on install.
- **`agent/install/setup_agent.ps1.template`** — Windows equivalent. Scans pip, npm, `tasklist`, Edge + Chrome history. Registers `PatronAI-Scan` Task Scheduler entry (every 30 min) alongside existing `PatronAI-Heartbeat`.
- Both templates now carry `SCAN_PUT_URL` and `AUTHORIZED_GET_URL` presigned URL placeholders.

#### New: Per-user authorised domains whitelist
- **`src/store/agent_store.py`** v1.6.0 — `create_package()` accepts `authorized_domains: list`; stores in `meta.json` and uploads `authorized.csv` to `config/HOOK_AGENTS/{token}/authorized.csv`. `get_presigned_urls()` returns `authorized_get_url` (presigned GET, 7-day TTL) alongside existing URLs. New `get_authorized_domains(token)` reads current list from meta.json. New `update_authorized_domains(token, domains)` overwrites `authorized.csv` and patches `meta.json` — agent picks up changes within 30 min without reinstalling.
- **`scripts/render_agent_package.py`** v1.4.0 — adds `authorized_domains: list` parameter; passes `AUTHORIZED_GET_URL` and `AUTHORIZED_DOMAINS` (fallback) to both template renders; passes `authorized_domains` to `create_package()`.
- **On each scan run** the agent fetches a fresh `authorized.csv` from S3 via `AUTHORIZED_GET_URL`. Falls back to local `~/.patronai/authorized_domains` if the presigned URL has expired.

#### New: EC2-side DMG and EXE artifact builders
- **`scripts/build_agent_artifacts.py`** (new, v1.0.0) — `_build_macos_dmg()` uses `genisoimage -apple -R` to create an HFS hybrid disk image on Linux. Stages a `.command` file inside (double-click opens Terminal on macOS). `_build_windows_exe()` writes an NSIS script and runs `makensis` to produce a silent self-extracting EXE. Both upload directly to S3 under the token prefix.
- **`Dockerfile`** — added `genisoimage` and `nsis` to system dependencies. Both available in EC2 container at generation time.
- **`scripts/render_agent_package.py`** — both builders called unconditionally after second-pass render. Result dict includes `dmg_url` and `exe_url` (presigned GET, 48h). Manual `build/build_dmg.sh` on Mac no longer required.
- **`src/store/agent_store.py`** — `get_artifact_url(key)` generates presigned GET URL for any S3 key (48h TTL). `delete_package()` now uses `list_objects_v2` + `delete_objects` to purge all objects under `config/HOOK_AGENTS/{token}/` prefix (covers sh, ps1, dmg, exe, meta, status, authorized.csv).

#### Deploy Agents UI
- **`dashboard/ui/tabs/deploy_agents.py`** v1.3.0 — added **Authorised tools** text area to the generate form (one domain per line). DMG and EXE download links shown inline after generation. Manual "Package Token" field removed.
- **`dashboard/ui/tabs/deploy_agents_table.py`** v1.1.0 — added **Whitelist** button per row. Expands an inline editor showing the current authorised domains loaded live from S3. Save calls `store.update_authorized_domains()` and confirms agent will pick up changes within 30 min.

#### Scan presigned URL
- **`src/store/agent_store.py`** — `get_presigned_urls()` now returns 5 URLs: `installer_url`, `meta_url`, `status_put_url`, `heartbeat_put_url`, `scan_put_url`, `authorized_get_url`. Scan results land at `ocsf/agent/scans/{token}/latest.json` (overwritten each run, 7-day TTL PUT).

---

### Hook Agent Delivery — v1.0.0 (2026-04-19)

- **`scripts/render_agent_package.py`**: OTP generation (`secrets`), bcrypt hash, per-recipient installer rendering, presigned S3 GET + PUT URLs baked into template, SES email dispatch, catalog.json append. S3 prefix `config/HOOK_AGENTS/` (`HOOK_AGENTS_PREFIX` constant).
- **`scripts/setup_hook_agents.sh`**: post-deploy one-time setup. Creates catalog.json, validates S3 write to `config/HOOK_AGENTS/`, checks SES identity.
- **`agent/install/setup_agent.sh.template`**: Mac/Linux OTP-locked installer. Checks dependencies, prompts OTP, validates bcrypt hash, checks expiry, writes `~/.patronai/config.json`, installs git pre-commit hook across repos, schedules heartbeat (launchd on Mac, cron on Linux), fires presigned PUT status.json.
- **`agent/install/setup_agent.ps1.template`**: Windows PowerShell equivalent.
- **`agent/install/README.md`**: End-user install guide for Mac/Linux curl, macOS DMG, Windows PowerShell, verify, uninstall.
- **`build/build_dmg.sh`**: macOS-only DMG builder. Wraps rendered `.sh` in an `.app` bundle, packages with `hdiutil create -format UDZO`. Skips gracefully on Linux. Run on admin's Mac after containers are up.
- **`dashboard/ui/tabs/deploy_agents.py`**: Admin form (Name, Email, Platform, Expiry); calls `render_agent_package.generate_package()`; live status table polling `store.list_catalog()` + `store.refresh_statuses()`.
- **`src/normalizer/agent.py`**: HEARTBEAT event type added — `_parse_heartbeat()` returns `outcome="HEARTBEAT"`, `severity="CLEAN"`, fields: device_id, os_name, os_version, agent_version, uptime_seconds.

### PatronAI User Interface — v2.1.0 (2026-04-19)

- **Support role**: `SUPPORT_EMAILS` env var; sidebar detects `is_support`; Support view menu item added; `dashboard/ui/support_view.py` + 4 sub-tabs (Rules, Code Signals, Coverage, Health).
- **Support tab files**: `support_tab_rules.py`, `support_tab_signals.py`, `support_tab_coverage.py`, `support_tab_health.py` — all new.
- **Deploy Agents tab**: wired as sixth tab in admin Settings panel (`ghost_dashboard.py`).
- **`_build_store()` DRY helper**: extracted in `ghost_dashboard.py` to avoid duplicated BlobIndexStore instantiation.

### PatronAI User Interface — v2.0.0 (2026-04-19)

- **Rebrand**: renamed all Pam/Steve/human-name references to role names (Exec view, Manager view); removed customer-specific branding from user-visible UI; page title is now "PatronAI · User Interface".
- **Dark enterprise theme**: `.streamlit/config.toml` with Bloomberg/Palantir colour palette; DM Sans body + JetBrains Mono code labels; Streamlit chrome hidden via CSS injection.
- **Tabbed settings**: Settings view split into Scanning · Alerting · Identity · Provider Lists · Users; each tab ≤150 lines; every save writes an audit record to `ocsf/audit/{YYYY}/{MM}/{DD}/{epoch}-setting-change.json`.
- **Role-based access**: non-admin users see Exec view + Provider Lists (read-only) only; admin users see all views including full Settings.
- **ocsf_bucket bug fix**: `settings_store.read()` now restores `ocsf_bucket` from `MARAUDER_SCAN_BUCKET` env if S3 settings contain an empty string; regression test added in `tests/test_settings.py`.

### UI Fixes — 2026-04-19

- **Sidebar contrast**: background `#010409` → `#0D1117`; all sidebar text tokens bumped to `#C9D1D9`; radio button active/hover CSS fixed — text was unreadable on black. (`dashboard/ui/styles.py` v1.1.0)
- **Absolute Grafana URL**: "Open dashboard" link now builds absolute URL via `GRAFANA_URL` env var or `PUBLIC_HOST` + `/grafana` path — no more blank screen from relative URL resolving against Streamlit port. (`dashboard/ui/sidebar.py` v1.1.0)
- **7-day data lookback**: `data.py` walks back up to 7 days for findings before falling to demo. Full stderr logging of each S3 attempt. Demo badge changed to red pill "DEMO DATA — S3 NOT CONNECTED". (`dashboard/ui/data.py` v1.1.0)
- **Sankey chart readability**: link opacity scales with value (`min(0.15 + v/max*0.5, 0.65)`), `font.size=13`, wider margins (l=120, r=120). (`dashboard/ui/exec_tab_exposure.py` v1.0.1)
- **Manager risk table**: replaced static HTML table with `st.dataframe(on_select="rerun", selection_mode="multi-row")`; resolve/escalate/email buttons call real S3, Trinity, and SES respectively. (`dashboard/ui/manager_tab_risks.py` v1.1.0, `manager_tab_actions.py` NEW)
- **CSV export**: single-click `st.download_button` — was double-click. (`dashboard/ui/manager_tab_logs.py` v1.1.0)

### Infrastructure — 2026-04-19

- **nginx**: default route changed to Streamlit (was Grafana); `/grafana/` location adds `X-Forwarded-Prefix /grafana` header; direct ports 8501/3000 no longer exposed. (`nginx/nginx.conf` v1.1.0)
- **docker-compose**: added env vars — `PUBLIC_HOST`, `GRAFANA_URL`, `SUPPORT_EMAILS`, `ALERT_RECIPIENTS`, `PATRONAI_FROM_EMAIL`, `GF_SERVER_ROOT_URL`, `GF_SERVER_SERVE_FROM_SUB_PATH=true`.
- **setup.sh**: auto-detects EC2 public IP via instance metadata; writes `PUBLIC_HOST` and `GRAFANA_URL` to `.env`; writes `ALERT_RECIPIENTS=` and `PATRONAI_FROM_EMAIL=noreply@patronai.ai`.
- **iam-policy.json**: added `HookAgentsDelivery` statement (scoped S3 on `*/config/HOOK_AGENTS/*`) and `HookAgentsSES` statement (`ses:SendEmail`, `ses:SendRawEmail`, `ses:GetIdentityVerificationAttributes`).

### Provider List Updates — 2026-04-19

- `config/unauthorized.csv`: added n8n Cloud, Langflow, Dify, sim.ai, Google Opal (5 new providers, total 75+).
