# =============================================================
# FILE: ~/.patronai/diagnose.ps1  (after install — installer copies this here)
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: One-command self-test for Windows hook-agent recipients.
#          Mirrors agent/install/diagnose.sh.
# USAGE:   powershell -ExecutionPolicy Bypass -File ~/.patronai/diagnose.ps1
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Step 0 — local diagnostics.
# =============================================================
$ErrorActionPreference = "Continue"

$AgentDir = Join-Path $env:USERPROFILE ".patronai"
$Cfg      = Join-Path $AgentDir "config.json"
$Log      = Join-Path $AgentDir "agent.log"

Write-Host "PatronAI agent — diagnostic report"
Write-Host "============================================="
Write-Host ("now: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"))
Write-Host ""

if (-not (Test-Path $Cfg)) {
    Write-Host "✗ Config not found at $Cfg. Agent may not be installed."
    exit 1
}

Write-Host "── identity (config.json) ──"
$C = Get-Content $Cfg | ConvertFrom-Json
foreach ($k in "token","email","device_uuid","mac_primary","company","bucket","region") {
    Write-Host ("  {0,-14} : {1}" -f $k, $C.$k)
}
Write-Host ""

Write-Host "── current local IPs ──"
try {
    $Ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            Select-Object -ExpandProperty IPAddress -Unique) -join ", "
    Write-Host ("  " + $Ips)
} catch { Write-Host "  (unable to enumerate)" }
Write-Host ""

Write-Host "── URL files present? ──"
foreach ($f in "heartbeat_url.txt","scan_url.txt","authorized_url.txt","urls_refresh_url.txt") {
    $P = Join-Path $AgentDir $f
    if ((Test-Path $P) -and ((Get-Item $P).Length -gt 0)) {
        Write-Host "  ✓ $f"
    } else {
        Write-Host "  ✗ $f MISSING"
    }
}
Write-Host ""

Write-Host "── last 20 entries in agent.log ──"
if (Test-Path $Log) {
    Get-Content $Log -Tail 20 | ForEach-Object { Write-Host ("  " + $_) }
} else {
    Write-Host "  agent.log missing — agent has never run, or log was deleted."
}
Write-Host ""

Write-Host "── live PUT probe (heartbeat URL) ──"
$UrlFile = Join-Path $AgentDir "heartbeat_url.txt"
if (Test-Path $UrlFile) {
    $HbUrl = (Get-Content $UrlFile).Trim()
    $Body  = '{"event_type":"DIAGNOSTIC_PROBE","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ") + '"}'
    try {
        $Resp = Invoke-WebRequest -Uri $HbUrl -Method Put -Body $Body `
                -ContentType "application/json" -TimeoutSec 15 -UseBasicParsing
        Write-Host ("  HTTP " + $Resp.StatusCode + " from heartbeat URL")
        if ($Resp.StatusCode -eq 200 -or $Resp.StatusCode -eq 201) {
            Write-Host "  ✓ S3 accepted the PUT — auth + network OK"
        }
    } catch {
        $Code = 0
        if ($_.Exception.Response) { $Code = [int]$_.Exception.Response.StatusCode }
        Write-Host ("  HTTP " + $Code + " — " + $_.Exception.Message)
        if ($Code -eq 403)        { Write-Host "  ✗ 403 — presigned URL likely EXPIRED. Re-issue installer." }
        elseif ($Code -eq 0)      { Write-Host "  ✗ network unreachable — corporate firewall / DNS / VPN issue" }
    }
}
Write-Host ""
Write-Host "============================================="
Write-Host "Send this output back to IT if anything is ✗."
