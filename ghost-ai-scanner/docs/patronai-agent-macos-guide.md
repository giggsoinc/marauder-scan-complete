# PatronAI Agent - macOS Installation Guide

> **Note:** This guide supersedes the previous `patronai-agent-macos-guide.html` which
> described a planned .app bundle + Jamf deployment that has not been implemented.
> The actual macOS delivery is via a bash script as documented below.

## Prerequisites

- macOS 12 (Monterey) or later
- Python 3 (Homebrew or python.org — NOT the Apple CLT stub)
- curl (pre-installed on macOS)
- git

## Installation

1. **Check your email** — you'll receive a download link + 6-digit OTP from the admin.

2. **Open Terminal** and run:
   ```bash
   curl -fsSL "<link-from-email>" -o setup_agent.sh && bash setup_agent.sh
   ```

3. **Enter the 6-digit OTP** when prompted (input is hidden for security).

4. **Done.** The agent is now running.

## What gets installed

| Item | Location |
|---|---|
| Config + scripts | `~/.patronai/` |
| Heartbeat job | `~/Library/LaunchAgents/com.patronai.heartbeat.plist` |
| Scan job | `~/Library/LaunchAgents/com.patronai.scan.plist` |
| Git pre-commit hooks | Symlinked in all repos under `$HOME` + `/Volumes` |
| Git template dir | `~/.patronai/git-template/` (auto-hooks new repos) |

## macOS 13+ (Ventura/Sonoma/Sequoia) — Background Items

After installation, macOS will show a notification:
**"PatronAI Background Items Added"**

Ensure it stays **enabled** in:
**System Settings → General → Login Items & Extensions → Allow in the Background**

If disabled, heartbeat and scan will silently stop running.

## Gatekeeper (if using DMG)

If you downloaded the `.dmg` and macOS shows:
*"can't be opened because it is from an unidentified developer"*

**Fix:** Right-click the `.command` file → **Open** → click **Open** in the dialog.

Or run directly in Terminal:
```bash
bash /Volumes/PatronAI\ Agent/PatronAI-Agent-YourName.command
```

## Verify installation

```bash
# Check launchd jobs
launchctl list | grep patronai

# Check log
cat ~/.patronai/agent.log

# Run diagnostics
bash ~/.patronai/diagnose.sh
```

## Uninstall

```bash
bash uninstall_agent.sh
```

No sudo required. Only removes PatronAI artifacts. Your code and repos are not affected.
The server is automatically notified of the uninstall.

## Troubleshooting

| Issue | Fix |
|---|---|
| "python3 requires command line developer tools" | Install Python via `brew install python` instead |
| "Cannot install bcrypt" (PEP 668) | Script handles this automatically with `--user` flag |
| Heartbeat/scan not running | Check System Settings → Login Items → PatronAI enabled |
| agent.log empty | Run `bash ~/.patronai/diagnose.sh` and send output to IT |
