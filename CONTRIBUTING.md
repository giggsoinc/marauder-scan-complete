# Contributing to PatronAI

Thank you for your interest in contributing to PatronAI — open-source AI endpoint
monitoring for shadow AI, ghost AI, and unmanaged LLM usage.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating you agree to uphold these standards.

---

## Ways to Contribute

| Type | Description |
|------|-------------|
| **Bug reports** | Open a [bug report](.github/ISSUE_TEMPLATE/bug_report.yml) |
| **Feature requests** | Open a [feature request](.github/ISSUE_TEMPLATE/feature_request.yml) |
| **Provider additions** | Add a row to a CSV — no code needed (see below) |
| **Documentation** | Fix errors, improve clarity, add examples |
| **Tests** | Add unit tests for uncovered code paths |

---

## Local Setup

### Prerequisites

- Python 3.12 or 3.13
- Git
- Docker (optional — only needed for full regression suite)

### Steps

```bash
# 1. Fork and clone
git clone https://github.com/giggsoinc/patronai.git
cd patronai

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r ghost-ai-scanner/requirements.txt

# 4. Install test extras
pip install pytest pytest-cov moto[s3,sts]

# 5. Run unit tests to verify your setup
pytest ghost-ai-scanner/tests/unit/ -q
```

A clean run should report **353 tests passed** in roughly 40 seconds with no
Docker or AWS credentials required.

---

## Running Tests

### Unit tests only (no Docker, no AWS credentials)

```bash
pytest ghost-ai-scanner/tests/unit/ -q
```

### Full regression suite (requires Docker + LocalStack)

```bash
cd ghost-ai-scanner
bash scripts/run_regression.sh
```

The regression script starts LocalStack automatically, runs all unit and
integration tests, and writes an HTML report to `reports/`.

Optional flags:

```
--keep-localstack     leave LocalStack running after the suite finishes
--unit-only           skip integration tests (same as running pytest directly)
--no-docker-build     skip rebuilding the PatronAI Docker image
```

---

## Code Standards

All contributions must meet these standards. PRs that violate them will be asked
to revise before merge.

### File size cap

**Maximum 150 lines per file.** If a file grows beyond 150 lines, split it into
logically separate modules. This is a hard limit enforced during review.

### Type hints

**Every function must have type hints on all parameters and the return value.**

```python
# Correct
def count_tokens(text: str, model: str = "gpt-4.1-mini") -> int:
    ...

# Wrong — missing return type and parameter type
def count_tokens(text, model="gpt-4.1-mini"):
    ...
```

### Error handling

**Every external call must be wrapped in try/except.** External calls include:
network requests, S3/AWS SDK calls, file I/O, subprocess calls, and any third-party
library call that can raise.

```python
# Correct
try:
    response = s3.get_object(Bucket=bucket, Key=key)
except ClientError as exc:
    logger.error("S3 read failed: %s", exc)
    return None
```

### File header + audit log

Every file must open with a header block and an audit log table:

```python
# =============================================================
# FILE: src/my_module.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: YYYY-MM-DD
# OWNER: Giggso Inc
# PURPOSE: One-line description of what this file does.
# AUDIT LOG:
#   v1.0.0  YYYY-MM-DD  Initial.
# =============================================================
```

When you modify an existing file, add a row to its audit log table.

### Function comments

Every function must have a docstring or inline comment explaining what it does,
its parameters, and its return value.

### No credentials in source

Never hardcode API keys, secrets, or credentials. Use `.env` and `python-dotenv`.
The `.env` file is gitignored — never commit it.

---

## Adding a New AI Provider to the Deny List

This is the **simplest and most impactful contribution** — it requires no Python
coding, no tests, and no infrastructure changes. The scanner reloads the CSV on
every scan cycle.

### Which file to edit

| Use case | File |
|----------|------|
| Network-layer detection (domain / port) | `ghost-ai-scanner/config/unauthorized.csv` |
| Code-pattern detection (import / API call in source) | `ghost-ai-scanner/config/unauthorized_code.csv` |

### CSV row format — `unauthorized.csv`

```
name,category,domain,port,severity,notes
```

| Column | Description | Example |
|--------|-------------|---------|
| `name` | Human-readable provider name | `Mistral AI` |
| `category` | Provider category | `Major LLM APIs` |
| `domain` | Domain or glob pattern | `api.mistral.ai` or `*.mistral.ai` |
| `port` | TCP port (almost always `443`) | `443` |
| `severity` | `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` | `HIGH` |
| `notes` | Optional free-text context | `Direct call bypasses Trinity` |

#### Example row

```csv
Mistral AI,Major LLM APIs,api.mistral.ai,443,HIGH,
```

### Severity guide

| Severity | When to use |
|----------|-------------|
| `CRITICAL` | Exfiltration risk, no audit trail, data-handling concern |
| `HIGH` | Unmanaged SaaS LLM, bypasses enterprise controls |
| `MEDIUM` | Internal tooling with LLM dependency, low external exposure |
| `LOW` | Developer tooling, local/on-prem, minimal risk |

### Before submitting a provider PR

1. Confirm the domain is publicly documented (link the source in the `notes` field
   or the PR description).
2. Run `pytest ghost-ai-scanner/tests/unit/test_rule_csv_validity.py -v` to verify
   the CSV parses correctly.
3. Check for duplicate rows before adding.

To report a provider that needs detection work beyond a CSV row, open a
[provider detection issue](.github/ISSUE_TEMPLATE/provider_detection.yml).

---

## Pull Request Checklist

Before opening a PR, confirm all items below:

- [ ] All 353 unit tests pass: `pytest ghost-ai-scanner/tests/unit/ -q`
- [ ] No file exceeds 150 lines
- [ ] All new functions have type hints on parameters and return values
- [ ] Every new external call is wrapped in try/except
- [ ] Modified files have an updated audit log row
- [ ] Every new function has a docstring or explanatory comment
- [ ] No credentials, tokens, or secrets are present in any committed file
- [ ] If adding a provider: CSV row format is correct and domain is publicly documented
- [ ] PR description explains WHAT changed, WHY it was needed, and HOW it was done

---

## Questions?

Open a [GitHub Discussion](https://github.com/giggsoinc/patronai/discussions) —
the maintainers check regularly and welcome questions at any level.
