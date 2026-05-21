# =============================================================
# PatronAI — Agent Uninstaller (Windows / PowerShell)
# Removes all PatronAI hooks, scheduled tasks, and agent files.
# Safe to run multiple times. No admin rights required.
# Only removes PatronAI artifacts — nothing else is touched.
# USAGE: powershell -ExecutionPolicy Bypass -File uninstall_agent.ps1
# =============================================================

$ErrorActionPreference = "Continue"
$AgentDir = Join-Path $env:USERPROFILE ".patronai"

function _info { param($msg) Write-Host "[patronai] $msg" }
function _ok   { param($msg) Write-Host "[patronai] + $msg" -ForegroundColor Green }

Write-Host ""
Write-Host "PatronAI Agent Uninstaller"
Write-Host "=========================="
Write-Host "This will remove the PatronAI agent from this machine."
Write-Host "Your code and git repos are NOT affected."
Write-Host ""
$confirm = Read-Host "Continue? [y/N]"
if ($confirm -notmatch "^[Yy]$") { Write-Host "Aborted."; exit 0 }
Write-Host ""

# ── 0. Notify server of uninstall (before deleting config) ───
$ConfigPath = Join-Path $AgentDir "config.json"
$HbUrlFile  = Join-Path $AgentDir "heartbeat_url.txt"
if ((Test-Path $ConfigPath) -and (Test-Path $HbUrlFile)) {
    try {
        $Cfg   = Get-Content $ConfigPath | ConvertFrom-Json
        $HbUrl = (Get-Content $HbUrlFile).Trim()
        if ($HbUrl -and $Cfg.token) {
            $Payload = @{
                event_type    = "UNINSTALLED"
                status        = "uninstalled"
                device_id     = $env:COMPUTERNAME
                device_uuid   = $Cfg.device_uuid
                email         = $Cfg.email
                token         = $Cfg.token
                company       = $Cfg.company
                uninstalled_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
            } | ConvertTo-Json -Compress
            Invoke-WebRequest -Uri $HbUrl -Method Put -Body $Payload `
                -ContentType "application/json" -TimeoutSec 15 -UseBasicParsing | Out-Null
            _ok "Server notified of uninstall."
        }
    } catch {
        _info "Could not notify server (non-fatal) - continuing uninstall."
    }
}

# ── 1. Unregister scheduled tasks (only PatronAI tasks) ──────
foreach ($task in @("PatronAI-Heartbeat", "PatronAI-Scan")) {
    if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
        _ok "Removed scheduled task: $task"
    }
}

# ── 2. Remove git pre-commit hooks (only if they reference patronai) ──
$removed = 0
Get-ChildItem -Path $env:USERPROFILE -Recurse -Depth 6 `
    -Filter ".git" -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $hook = Join-Path $_.FullName "hooks\pre-commit"
    if (Test-Path $hook) {
        $content = Get-Content $hook -Raw -ErrorAction SilentlyContinue
        if ($content -and $content -match "patronai") {
            Remove-Item $hook -Force
            # Restore original hook if backup exists
            $backup1 = "${hook}.pre-patronai-backup"
            $backup2 = "${hook}.backup"
            if (Test-Path $backup1) {
                Move-Item $backup1 $hook
                _ok "Restored original hook in: $($_.Parent.FullName)"
            } elseif (Test-Path $backup2) {
                Move-Item $backup2 $hook
                _ok "Restored original hook in: $($_.Parent.FullName)"
            } else {
                _ok "Removed hook from: $($_.Parent.FullName)"
            }
            $removed++
        }
    }
}
_info "Hooks removed from $removed repositories."

# ── 3. Unwire git template dir (only if it points to patronai) ──
$tmplDir = git config --global init.templateDir 2>$null
if ($tmplDir -and $tmplDir -match "\.patronai") {
    git config --global --unset init.templateDir 2>$null
    _ok "Cleared git init.templateDir (was: $tmplDir)"
} elseif ($tmplDir) {
    # Check if the external templateDir has our hook
    $extHook = Join-Path $tmplDir "hooks\pre-commit"
    if (Test-Path $extHook) {
        $extContent = Get-Content $extHook -Raw -ErrorAction SilentlyContinue
        if ($extContent -and $extContent -match "patronai") {
            Remove-Item $extHook -Force
            _ok "Removed PatronAI hook from external templateDir ($tmplDir)"
        }
    }
}

# ── 4. Remove agent directory ─────────────────────────────────
if (Test-Path $AgentDir) {
    Remove-Item -Recurse -Force $AgentDir
    _ok "Removed $AgentDir"
}

Write-Host ""
_info "Uninstall complete. No agent files remain on this machine."
_info "To deregister from the server, ask your admin to delete your entry in:"
_info "  Settings -> Deploy Agents -> Delete button on your row."
