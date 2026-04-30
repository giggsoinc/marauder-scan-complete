# Chat data backend — hourly S3 rollups

The PatronAI chat panel does not query raw `findings/...jsonl` at request
time. It reads small pre-aggregated dimension files written hourly. This
document explains what those files are, where they live, and how to
operate the system.

---

## Why rollups

The 8 chat tools (`get_shadow_ai_census`, `get_top_risky_users`, …) need
aggregations like *"top 20 AI providers in the last 90 days, with hits and
distinct user counts"*. Doing that against raw events scales linearly with
event volume — bad for HUGE-tenant deployments.

Rollups precompute the dimensions the chat actually asks for. A 30-day
*"top providers"* answer reads 30 × 24 = 720 small JSON files (kilobytes
each) and merges them in Python. Volume-independent: file size depends on
*cardinality* (number of distinct providers / users), not raw event count.

No vector store, no embeddings, no Athena. Pure S3 + Python.

---

## S3 layout

```
s3://{MARAUDER_SCAN_BUCKET}/
  findings/{YYYY}/{MM}/{DD}/{severity}.jsonl              ← raw flat events (existing)
  users/{sha256(email)[:16]}/rollup/{YYYY}/{MM}/{DD}/{HH}/
    by_provider.json    (gzipped)
    by_severity.json
    by_device.json
    by_category.json
    _meta.json
  tenants/{sha256(company)[:16]}/rollup/{YYYY}/{MM}/{DD}/{HH}/
    by_provider.json
    by_user.json        (only present in tenant tree)
    by_severity.json
    by_device.json
    by_category.json
    _meta.json
  rollup-meta/unknown_providers.jsonl                     ← audit log
```

Each `by_*.json` is a small dictionary keyed by the dimension value.
Example `by_provider.json`:

```json
{
  "OpenAI ChatGPT": {
    "hits": 47, "users": ["alice@x.com", "bob@x.com"],
    "user_count": 2, "device_count": 2,
    "categories": {"browser": 47},
    "by_severity": {"HIGH": 47},
    "first_seen": "2026-04-29T10:00:00+00:00",
    "last_seen":  "2026-04-29T10:55:00+00:00"
  },
  "GitHub Copilot": { ... }
}
```

`_meta.json` records `{rows_processed, run_started_at, run_completed_at,
scope, scope_id, owner_email|company_name}` so an operator can spot stale
or partial windows without opening the dimension files.

---

## Scope routing

The chat picks which tree to read based on the dashboard view:

| View                          | Scope    | Reads from                         |
|-------------------------------|----------|------------------------------------|
| `exec`                        | `user`   | `users/{sha256(email)[:16]}/...`   |
| `manager`, `support`, `home`  | `tenant` | `tenants/{sha256(company)[:16]}/...` |

The hourly job writes both trees in a single pass over the day's
`findings/...jsonl`, so scope-routing is just a path choice at read time.

---

## Provider name normalisation

Raw rows from `agent_explode.py` have ugly provider strings:
`claude.ai`, `github.copilot`, `pip:openai`, `mcp:claude_desktop:fs`.
The rollup job runs every row through
`src/normalizer/provider_names.py:normalize_provider(category, raw)`
which:

1. For `category=="browser"`, looks up the domain in
   `config/unauthorized.csv` (tenant-curated). Missing → falls back to a
   built-in `_KNOWN_AI_TOOLS` dict.
2. For other categories, looks up the raw provider in the built-in dict.
3. On miss, returns the raw provider as-is and appends a row to
   `s3://{bucket}/rollup-meta/unknown_providers.jsonl` for later
   dictionary expansion.

This is why chat answers say *"OpenAI ChatGPT"* instead of *"chatgpt.com"*.

---

## Citations

Every successful tool result includes a `_citation` block:

```json
"_citation": {
  "source":          "S3 hourly rollups",
  "scope":           "tenant",
  "scope_id":        "abc1234…",
  "window":          {"start": "2026-04-01T00:00:00+00:00",
                      "end":   "2026-05-01T00:00:00+00:00"},
  "dimensions":      ["by_provider"],
  "rows_aggregated": 1098,
  "s3_path_pattern": "s3://patronai/tenants/abc.../rollup/.../by_provider.json"
}
```

The system prompt instructs the LLM to surface a `**Sources:**` footer in
every answer listing the `s3_path_pattern` from each tool call. If a user
ever doubts a number, they can verify it in S3.

When rollups are empty for the requested scope/window, tools return a
`{no_data: true, _message, _citation}` envelope. The LLM is instructed
to relay this honestly rather than fabricate.

---

## Operations

### Schedule

`main.py` launches `src/jobs/hourly_rollup.py:scheduler_loop` as a daemon
thread. It fires at `:05` of every UTC hour and processes the previous
full hour `[H-1:00, H:00)`.

### Catch-up on startup

Same module's `catch_up_rollups()` runs once when the container boots:

- If **rollups already exist**: process every missing hour from the
  latest-completed up to now-1h.
- If **no rollups exist** (first deploy): backfill the last
  `ROLLUP_INITIAL_BACKFILL_DAYS` days (default 7) so the chat has
  historical data immediately.

### Manual catch-up / backfill / single hour

```bash
# Fill anything missing up to the previous hour:
docker exec patronai python -m src.jobs.hourly_rollup --catch-up

# Process a specific hour:
docker exec patronai python -m src.jobs.hourly_rollup --hour 2026-04-29T15

# Wider historical backfill (idempotent — overwrites existing rollups):
docker exec patronai python -m src.jobs.hourly_rollup \
    --backfill --start 2026-01-01T00 --end 2026-04-30T00
```

### Spot-checking output

```bash
# List the rollup tree for a specific hour:
aws s3 ls s3://$MARAUDER_SCAN_BUCKET/tenants/$(echo -n "$COMPANY_NAME" \
    | shasum -a 256 | cut -c1-16)/rollup/2026/04/29/15/

# Read a provider dim:
aws s3 cp s3://$MARAUDER_SCAN_BUCKET/tenants/.../rollup/2026/04/29/15/by_provider.json - \
  | gunzip | jq

# Check what providers are unmapped (will surface as raw strings):
aws s3 cp s3://$MARAUDER_SCAN_BUCKET/rollup-meta/unknown_providers.jsonl - \
  | tail -50 | jq
```

### Configuration

| Env var                          | Default | Meaning                                          |
|----------------------------------|---------|--------------------------------------------------|
| `ROLLUP_HOURLY_OFFSET_MINUTES`   | `5`     | Minute past the hour to fire scheduled rollup.   |
| `ROLLUP_INITIAL_BACKFILL_DAYS`   | `7`     | First-deploy backfill window when no rollups.   |
| `CHAT_HISTORY_RETENTION_DAYS`    | `30`    | Lifecycle expiry on `chat/` prefix.             |
| `LLM_READ_TIMEOUT_S`             | `180`   | LLM HTTP read timeout (Thinking model needs >60s). |
| `LLM_MAX_TOKENS`                 | `1024`  | Per-completion output cap.                       |

### IAM

The bucket policy must grant the runtime role:

```json
"s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject",
"s3:GetBucketLifecycleConfiguration", "s3:PutBucketLifecycleConfiguration"
```

The last two are required so `ensure_lifecycle_policy()` can apply the
chat-history expiry rule on first boot. See `iam-policy.json`.

---

## Failure modes

- **Hourly job crashes once** — the watchdog in `main.py` will restart the
  container; the next boot's `catch_up_rollups()` fills the gap.
- **S3 Select fails on a `findings/.../*.jsonl`** — the rollup job falls
  back to `GetObject` + in-process filter for that key (logged).
- **Lifecycle apply fails** — non-fatal, logged. Re-run by restarting the
  container after fixing IAM.
- **LFM2.5-Thinking emits long reasoning** — `LLM_READ_TIMEOUT_S=180s`
  covers it. If you swap to a non-thinking model, you can lower it.

---

## What this doesn't replace

- `findings/...jsonl` is still the source of truth for raw events.
- The inventory dashboard tabs (`manager_view.py`, `support_view.py`,
  etc.) still read raw events via `dashboard/ui/data.py:load_data()`.
  Migrating those is out of scope for this phase — they pre-load
  bounded slices, not the full history, so they don't have the same
  scaling pressure as the chat.
