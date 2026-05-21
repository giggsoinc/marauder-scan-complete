# PatronAI — Agent Uninstall Scripts

Standalone uninstall scripts for all platforms. No admin/sudo required.
Safe to run multiple times. Only removes PatronAI artifacts.

## Usage

### Windows
```powershell
powershell -ExecutionPolicy Bypass -File uninstall_agent.ps1
```

### Mac / Linux
```bash
bash uninstall_agent.sh
```

## What gets removed

| Artifact | Windows | Mac | Linux |
|---|---|---|---|
| Scheduled tasks / jobs | `PatronAI-Heartbeat`, `PatronAI-Scan` | launchd plists | crontab entries |
| Git pre-commit hooks | Only if content references `patronai` | Only if symlink/content references `patronai` | Same as Mac |
| Git templateDir | Only if it points to `.patronai` | Same | Same |
| Agent directory | `%USERPROFILE%\.patronai\` | `~/.patronai/` | `~/.patronai/` |

## What is NOT touched

- Your source code
- Your git repositories (commits, branches, history)
- Other scheduled tasks / cron jobs
- Other git hooks not related to PatronAI
- System files, other applications, processes

## After uninstall

Ask your admin to deregister your agent from the server:
**Settings → Deploy Agents → Delete button on your row**
