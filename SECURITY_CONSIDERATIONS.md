# Security Considerations

> **Audience:** anyone deploying or operating PatronAI.
> **Scope:** every security-relevant decision made in this repo, what's been
> hardened, what's still open, and what an operator must do at deploy time.
> **Companion:** [`SECURITY.md`](SECURITY.md) covers vulnerability reporting.
> This file covers everything else.

---

## ⚠ Production Deployment — Read This First

> **🔒 LOCK DOWN ADMIN + GRAFANA ACCESS IN A SUBNET WITH CIDR LOCK-IN.**
> Streamlit (`:8501`), Grafana (`:3000`), and the SSH bastion to the EC2
> host MUST be reachable only from a known IP range. Default deployment
> exposes them on `0.0.0.0`. In production, restrict at the security-group
> / NACL / ALB level — never publish admin surfaces to the open internet.

> **🔒 ENABLE SSO AND MFA WHEN MOVING TO PRODUCTION GRADE.**
> The shipped auth gate is email-allowlist only ([`auth_gate.py`](ghost-ai-scanner/dashboard/ui/auth_gate.py),
> [`auth.py`](ghost-ai-scanner/dashboard/auth.py)). It is acceptable for
> single-tenant pilots behind a CIDR lock-in but **not for production**.
> Wire SSO (Google Workspace / Okta / Azure AD via OIDC or SAML) and
> require MFA at the IdP before going live.

These two controls together cut the attack surface by orders of magnitude.
Neither is enabled by default — both are explicit operator responsibilities.

---

## Settings to Enable Before Going Live

### GitHub repository settings
URL: `https://github.com/giggsoinc/PatronAI/settings/security_analysis`

| Setting | State | Why |
|---|---|---|
| **Secret scanning** | **Enable** | Periodic scan of the whole repo + all branches for known credential patterns. |
| **Push protection** | **Enable** | Refuses pushes containing detected secrets in real time. Single highest-impact control. |
| **Dependabot alerts** | **Enable** | Notifies on CVEs in pinned dependencies. |
| **Dependabot security updates** | **Enable** | Opens PRs to bump vulnerable deps automatically. |
| **Branch protection on `main`** | **Enable** | No force-push, require PR, require status checks. |
| **Required reviewers on PRs** | **≥ 1** | No solo merges into `main`. |

### AWS IAM settings (the runtime role)
| Setting | State | Notes |
|---|---|---|
| Long-lived access keys on `marauder-scan` user | **Avoid** | Prefer **EC2 Instance Profile** that the container assumes; rotates automatically, no `.env` secret to leak. |
| Key age | **≤ 90 days** | If you must use long-lived keys, rotate quarterly and audit usage in CloudTrail. |
| MFA on the AWS console root + admin users | **Required** | Hardware key (YubiKey) preferred. |
| Service Control Policy denying `iam:CreateUser`, `iam:CreateAccessKey` outside a break-glass window | **Recommended** | Stops accidental long-lived-key creation. |
| `s3:PutObjectAcl` on the PatronAI bucket | **Deny** | Bucket should be private; PatronAI never needs to set ACLs. |

### EC2 / VPC
| Setting | State | Notes |
|---|---|---|
| Security group on EC2 — port 22 (SSH) | **Source: bastion CIDR or VPN** | Never `0.0.0.0/0`. |
| Security group on EC2 — port 80/443 | **Source: ALB security group only** | Front everything with an ALB; don't expose nginx directly. |
| Security group on EC2 — port 8501 (Streamlit) | **Closed externally** | Reachable only from the same SG (nginx). |
| Security group on EC2 — port 3000 (Grafana) | **Closed externally** | Same as above. |
| Security group on EC2 — port 8080 (llama-server) | **Closed externally** | Reachable only from inside the container. |
| ALB listener | **HTTPS 443 only** | Redirect 80 → 443. ACM-managed certificate. |
| TLS minimum | **TLS 1.2** | Disable TLS 1.0 / 1.1. |
| VPC Flow Logs | **Enabled** | For incident forensics. |
| GuardDuty | **Enabled** in the account | Detects credential compromise. |

### Application secrets
| Setting | State | Notes |
|---|---|---|
| `GF_SECURITY_ADMIN_PASSWORD` in `.env` | **Required (no default)** | Compose now fails fast if missing. `setup.sh` auto-generates a random one if you hit Enter. |
| `.env` permissions | **`chmod 600`** | Set automatically by `setup.sh`. |
| `.env` location | **EC2 only** | Never commit; `.gitignore` blocks it. Local dev should not need it. |
| AWS keys | **Rotate ≤ 90 days** | Or use Instance Profile. |
| LLM API keys (`LLM_API_KEY`) when using cloud providers | **Store in AWS Parameter Store** under `/patronai/llm/api_key`, not in `.env`. | The transport already reads SSM as a fallback. |

---

## Audit Findings — Status as of 2026-05-01

These are the items found by `pip-audit`, `bandit`, `detect-secrets`, and
manual review during the OSS launch prep.

| # | Finding | Severity | Status | Reference |
|---|---|---|---|---|
| 1 | `fastmcp >=0.1.0,<1.0.0` allowed 0.4.1 with 6 CVEs (CVE-2025-62800, CVE-2025-62801, CVE-2025-64340, CVE-2025-69196, GHSA-rcfx-77hg-w2wv, CVE-2026-27124) | HIGH | ✅ **Fixed** | [`requirements.txt`](ghost-ai-scanner/requirements.txt) bumped to `>=3.2.0,<4.0.0`. MCP server stable surface preserved. |
| 2 | `agent/install/setup_agent.sh` committed to git, contained an AWS access key (`AKIA****ROTATED-2026-05-01****`, original ID redacted) in 7 presigned URLs (since initial commit) | HIGH | ✅ **Fixed** | Key rotated and **deleted** in IAM. File removed from HEAD. History purged via `git filter-repo`. Force-pushed to GitHub. Branch protection re-applied. New `.gitignore` rule blocks recurrence. The dead key ID is intentionally not reproduced in this doc to keep the secret-pattern scanner strict. |
| 3 | Dashboard auth is email-allowlist only — no password / OTP / SSO | MEDIUM | 🟡 **Open** (deferred) | See [`dashboard/ui/auth_gate.py`](ghost-ai-scanner/dashboard/ui/auth_gate.py), [`dashboard/auth.py`](ghost-ai-scanner/dashboard/auth.py). Mitigation: **CIDR lock-in + SSO + MFA at production**. Real fix is a separate PR (OAuth/SAML/OTP). |
| 4 | Public service exposure: Streamlit `:8501`, Grafana `:3000`, nginx plain `:80`. Grafana shipped with default `change-me` password | MEDIUM | 🟢 **Partial** | Grafana default password removed (compose + Dockerfile + setup.sh). Compose stack now refuses to start without `GF_SECURITY_ADMIN_PASSWORD`. Port mappings + TLS still need operator action — see "EC2 / VPC" table above. |
| 5 | S3 Select SQL string-construction in `findings_store.py` (potential injection on `owner` / `provider`) | MED/LOW | ✅ **Fixed** | `_sql_escape()` doubles single quotes, strips NUL/newline/backslash. `limit` clamped to `[1, 10000]`. Same hardening applied to `hourly_rollup.py:_sql_escape_iso()` for the timestamp filter. Both annotated `# nosec B608` with justification. |
| 6 | Streamlit binds `0.0.0.0` (Bandit B104) | INFO | ⚠ **Justified** | Required inside the container for nginx in front of it. Annotated `# nosec B104` with comment. Real threat (port exposure) tracked under #4. |
| 7 | `.claude/settings.local.json` flagged by `detect-secrets` as containing a likely GitHub token | INFO | ⚠ **Local-only** | File is `.gitignore`d at `.gitignore:5`, never tracked, exists only on developer laptop. **Operator must check + rotate any live PAT in that file.** |
| 8 | Test fixtures using AWS docs example `AKIAIOSFODNN7EXAMPLE` flagged by detect-secrets | INFO | ⚠ **Intentional** | Allow-listed in `tests/unit/test_secret_patterns.py` and the pre-commit hook. The string is the official AWS docs example, not a real credential. |

---

## Prevention Layers Added During Cleanup

These exist so the AWS-key leak (finding #2) cannot recur silently.

| | What | Where | Notes |
|---|---|---|---|
| P1 | `.gitignore` blocks `agent/install/setup_agent.{sh,ps1}` (rendered installers); allows `.template` files | [`ghost-ai-scanner/.gitignore`](ghost-ai-scanner/.gitignore) | First defense. |
| P2 | Local pre-commit hook scans staged content for AWS access-key shape (`AKIA…`+16), session-token shape (`ASIA…`+16), the presigned-URL signature fragment, the 40-char secret-shape paired with `AWS_SECRET_ACCESS_KEY=`, and the rendered installer file paths | [`ghost-ai-scanner/scripts/git-hooks/pre-commit`](ghost-ai-scanner/scripts/git-hooks/pre-commit) | Install: `bash ghost-ai-scanner/scripts/git-hooks/install.sh` (each developer, once after clone). Patterns intentionally described in prose (not literal regex) so this doc itself doesn't trigger the scanner. |
| P3 | CI test suite that walks every git-tracked text file and asserts no AWS-key patterns appear | [`ghost-ai-scanner/tests/unit/test_secret_patterns.py`](ghost-ai-scanner/tests/unit/test_secret_patterns.py) | 5 tests. Catches anyone bypassing P2 with `--no-verify`. |
| P4 | GitHub Secret Scanning | Repo settings | See "GitHub repository settings" above. |
| P5 | GitHub Push Protection | Repo settings | The single most effective control — refuses pushes that contain detected secrets at the door. |
| P6 | GitHub Dependabot | Repo settings | Catches the next #1-class issue automatically. |
| P7 | Branch protection on `main` (no force-push, PR required) | Repo Rulesets | Re-applied after the one-shot history rewrite of 2026-05-01. |

---

## Operational Practices

- **Rotate AWS access keys ≤ 90 days.** Better: switch to EC2 Instance Profile.
- **Rotate Grafana admin password ≤ 90 days.** Use `openssl rand -base64 24 | tr -d '/+=' | cut -c1-32`.
- **Rotate the GitHub PAT used for git operations** when team membership changes.
- **Audit CloudTrail monthly** for unexpected uses of the IAM user / role.
- **Review `s3://patronai/rollup-meta/unknown_providers.jsonl`** monthly — anything unexpected there indicates either a real new shadow-AI provider or a misconfigured agent.
- **Re-run `pip-audit` + `bandit` before every release.** Dependabot will catch most of it asynchronously, but a final pre-release scan is cheap.

## Incident Response

If you suspect a credential leak:

1. **Immediately rotate** the credential in AWS / GitHub / wherever it lives.
2. Search git history: `git log --all -p | grep -E "AKIA[A-Z0-9]{16}"`.
3. If the secret is in git history, follow the runbook at [`ghost-ai-scanner/docs/chat-rollups.md`](ghost-ai-scanner/docs/chat-rollups.md) (the `git filter-repo` flow we used for finding #2).
4. Force-push the cleaned history.
5. Notify everyone with a clone — they need to **re-clone**, not pull.
6. Audit CloudTrail / GitHub audit log for unauthorised use of the leaked secret.
7. Open a private security issue per [`SECURITY.md`](SECURITY.md).

---

## What This Document Does NOT Replace

- A formal threat model.
- A penetration test.
- SOC 2 / ISO 27001 controls.
- Your organisation's broader security policy.

It is the minimum-viable record of what's been considered in this codebase.
Keep it up to date as new findings land.
