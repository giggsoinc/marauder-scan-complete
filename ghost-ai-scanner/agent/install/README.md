# PatronAI Agent — Installation Guide

## What this installs

A lightweight git pre-commit hook that detects AI framework usage in your code commits and forwards a small diff snippet to your company's PatronAI scanner. No code leaves your machine during analysis — only the diff lines that match known AI patterns are forwarded.

The hook **never blocks commits**. It runs in the background, always exits 0.

---

## Before you start

| Requirement | Mac/Linux | Windows |
|-------------|-----------|---------|
| Python 3    | Built-in on most systems | [python.org](https://python.org) |
| curl        | Built-in | Built-in (Win10+) |
| AWS CLI     | Optional — needed for diff shipping | Optional |
| Your OTP    | From your install email | From your install email |

---

## Mac / Linux

```bash
# 1. Download your personalised installer (link from your email)
curl -fsSL "<your-download-link>" -o setup_agent.sh

# 2. Run it
bash setup_agent.sh

# 3. Enter your 6-digit OTP when prompted
```

That's it. The script installs the hook into all git repositories it finds under your home directory.

---

## Windows (PowerShell)

```powershell
# 1. Download your personalised installer (link from your email)
Invoke-WebRequest -Uri "<your-download-link>" -OutFile setup_agent.ps1

# 2. Run it
powershell -ExecutionPolicy Bypass -File setup_agent.ps1

# 3. Enter your 6-digit OTP when prompted
```

---

## What happens during install

1. Your OTP is validated locally against a bcrypt hash — it never leaves your machine in plain text.
2. A config file is written to `~/.patronai/config.json` (Mac/Linux) or `%USERPROFILE%\.patronai\config.json` (Windows).
3. A pre-commit hook script is written to `~/.patronai/pre_commit_hook.sh`.
4. The hook is symlinked into every `.git/hooks/` directory found (up to 4 levels deep from home).
5. Any existing `pre-commit` hook is backed up as `pre-commit.pre-patronai-backup`.

---

## Uninstalling

```bash
# Remove config and hook script
rm -rf ~/.patronai

# Remove hooks from repos (run inside each repo)
rm .git/hooks/pre-commit
# Restore backup if it existed
mv .git/hooks/pre-commit.pre-patronai-backup .git/hooks/pre-commit 2>/dev/null || true
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "OTP must be exactly 6 digits" | Check you copied all 6 digits from the email |
| "Installation package has expired" | Ask your IT admin to generate a new package |
| "Cannot reach installation server" | Check your internet connection; URL expired after 48h |
| "bcrypt not found" | Run `pip3 install bcrypt` then retry |
| Hook not running | Confirm `.git/hooks/pre-commit` exists and is executable (`chmod +x`) |

---

## Privacy

- The hook only activates when a commit contains AI framework patterns (import statements, API endpoints, SDK names).
- At most 5 KB of the diff is forwarded, stored in your company's private S3 bucket.
- No personal files, credentials, or environment variables are ever read or forwarded.
- The hook process runs asynchronously — commits are never delayed.
