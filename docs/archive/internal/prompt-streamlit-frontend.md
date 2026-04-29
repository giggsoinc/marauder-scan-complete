# Claude Code Prompt — PatronAI User Interface (Streamlit front end)

Paste this whole block into Claude Code inside the ghost-ai-scanner repo.

---

## Context

We are rebranding and de-technicalising the Streamlit app so it reads as the
**PatronAI User Interface** — the one place SecOps Managers and Platform Admins
use day-to-day. The app still runs on Streamlit under the hood, but the user
never sees the word "Streamlit", never sees a port, never sees a CSV filename.
Deployment model is **AWS Marketplace** — customer-side personas are Platform
Admin, SecOps Manager, Security Executive, Support Team, End User. No human
names (Steve / Pam / Ravi) anywhere in the UI.

Follow CLAUDE.md rules in this repo:
- Max 150 lines per file. If a change pushes a file past 150, split it.
- Every file needs a header comment block + audit log table.
- Type hints on all functions. try/except on every external call.
- Before writing code, print a short bullet plan (max 75 words).

## Files in scope

Look under `ghost-ai-scanner/` for the Streamlit app. Likely entry points:
- `streamlit_app.py` or `app.py` or `ui/app.py`
- `pages/` directory for multi-page apps
- any `.streamlit/config.toml`
- any CSS / theme files referenced by st.markdown

Find them with a quick grep for `import streamlit` and
`st.set_page_config`. Do not assume the path — discover it.

## Scope of changes (numbered)

1. **Branding**
   - Page title + browser tab: `PatronAI · User Interface`
   - App header: `PatronAI — User Interface` (no "Streamlit", no port)
   - Remove any "Powered by Streamlit", "Deploy" ribbon, hamburger menu
     (`st.set_page_config(menu_items={})` + CSS hide)
   - Favicon: reuse `assets/branding/patronai-icon.png` if present
   - Sidebar footer: `PatronAI · v1.1.0` (no Giggso, no human names)

2. **Dark enterprise theme** (Bloomberg Terminal meets Palantir — NOT generic AI)
   - Write `.streamlit/config.toml` with:
     - `base = "dark"`
     - `primaryColor = "#1F6FEB"`
     - `backgroundColor = "#0D1117"`
     - `secondaryBackgroundColor = "#161B22"`
     - `textColor = "#E6EDF3"`
     - `font = "sans serif"`
   - Inject CSS for DM Sans (body) + JetBrains Mono (code / labels)
   - Hide the default Streamlit header + footer via CSS

3. **Settings tabs** — use `st.tabs(["Scanning", "Alerting", "Identity",
   "Provider Lists", "Users"])`. Each tab renders user-facing labels only.
   - Scanning: Scan interval · Dedup window · Max files per cycle · Lookback
   - Alerting: Email channel · Trinity webhook · LogAnalyzer webhook
   - Identity: Priority order · SSO directory · LDAP source · Endpoint protection
     toggle
   - Provider Lists: Denylist (read-only, shows count + categories — sourced
     from the Marketplace rules channel; no edit) · Allow list (inline editor
     with `st.data_editor`)
   - Users: Invite email · Remove · Role badge

4. **Buttons on the home page**
   - `Force Rescan` — calls existing rescan handler. Show spinner + success.
   - `Refresh Now` — rebuild summary. Show spinner + timestamp after.
   - `Backfill` — open modal with date range. Submit triggers backfill job.
   Each button wraps the external call in try/except and logs to stderr.

5. **De-technicalise the UI copy**
   - Replace every "unauthorized.csv" → "Denylist"
   - Replace every "authorized.csv" → "Allow list"
   - Replace every "settings.json" in visible text → "Settings"
   - Replace every "S3 bucket" in visible text → "Tenant storage"
   - Replace every "SNS" in visible text → "Alert channel"
   - Remove any raw file paths, env var names, docker / container mentions
   - Replace GF_SECURITY_ADMIN_PASSWORD prompts with "Admin password"

6. **No human names anywhere**
   - grep the codebase for `Steve`, `Pam`, `Ravi`, `steve`, `pam`, `ravi`
   - Replace dashboard labels with role-only: `Manager view`, `Exec view`
   - Replace comments referencing people with role names

7. **Fix the settings.json ocsf_bucket empty-string bug**
   - Current behaviour: when `ocsf_bucket` is `""`, scanner falls back to
     the wrong path and pipeline goes silent.
   - Fix in the settings save path: if the UI field is blank, write the
     default bucket name (read from `GHOST_AI_BUCKET` env) — never an empty
     string. Validate on load too.
   - Add a regression test in `tests/test_settings.py` that asserts
     `load_settings()` never returns `ocsf_bucket == ""`.

8. **Role-based access**
   - Read role from existing auth layer (don't invent a new one).
   - SecOps Manager + Platform Admin: full settings access.
   - Security Executive: read-only on Provider Lists, no access to Scanning /
     Alerting / Identity tabs. Hide the tabs entirely — don't just disable.
   - Support Team: same as Platform Admin.

9. **Audit trail**
   - Every settings save writes one line to
     `ocsf/audit/{YYYY}/{MM}/{DD}/{epoch}-setting-change.json` with
     `user · field · old · new · timestamp`. Use the existing S3 helper.

## Constraints

- Do not change scanner code unless strictly required by item 7 (settings bug).
- Do not introduce new dependencies. Streamlit, boto3, Polars only.
- No network call in the main thread of the UI — everything goes through
  existing async / cached helpers.
- Keep each file under 150 lines. Split into `ui/tabs/scanning.py`,
  `ui/tabs/alerting.py`, etc. if needed.

## Deliverables

1. One bullet plan (under 75 words) printed before any code.
2. File-by-file diff — every touched file with a short rationale.
3. Updated `.streamlit/config.toml`.
4. New or updated CSS injection block.
5. `tests/test_settings.py` regression test.
6. A 5-line CHANGELOG entry in `CHANGELOG.md` under a `## [Unreleased]` header.
7. Do NOT `docker-compose up` or restart services — leave that to the human.

## Verification

At the end, print:
- List of every file created / modified
- Grep results confirming zero remaining occurrences of: `Streamlit`,
  `Grafana`, `Steve`, `Pam`, `Ravi`, `:8501`, `:3000`, `unauthorized.csv`,
  `authorized.csv`, `GF_SECURITY_ADMIN_PASSWORD` in user-visible strings
  (code comments and logs are fine)
- Exit code of `pytest tests/test_settings.py`

Do not commit. Leave the working tree ready for me to review with `git diff`.
