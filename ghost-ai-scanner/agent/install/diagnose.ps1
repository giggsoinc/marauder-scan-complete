# =============================================================
# PatronAI Agent - Diagnostic Script (Windows)
# USAGE: powershell -ExecutionPolicy Bypass -File ~/.patronai/diagnose.ps1
# =============================================================
$ErrorActionPreference = "Continue"

$AgentDir = Join-Path $env:USERPROFILE ".patronai"
$Cfg      = Join-Path $AgentDir "config.json"
$Log      = Join-Path $AgentDir "agent.log"

Write-Host "PatronAI agent - diagnostic report"
Write-Host "============================================="
Write-Host ("now: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"))
Write-Host ""

if (-not (Test-Path $Cfg)) {
    Write-Host "[FAIL] Config not found at $Cfg. Agent may not be installed."
    exit 1
}

Write-Host "-- identity (config.json) --"
$C = Get-Content $Cfg | ConvertFrom-Json
foreach ($k in "token","email","device_uuid","mac_primary","company","bucket","region") {
    Write-Host ("  {0,-14} : {1}" -f $k, $C.$k)
}
Write-Host ""

Write-Host "-- current local IPs --"
try {
    $Ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            Select-Object -ExpandProperty IPAddress -Unique) -join ", "
    Write-Host ("  " + $Ips)
} catch { Write-Host "  (unable to enumerate)" }
Write-Host ""

Write-Host "-- URL files present? --"
foreach ($f in "heartbeat_url.txt","scan_url.txt","authorized_url.txt","urls_refresh_url.txt") {
    $P = Join-Path $AgentDir $f
    if ((Test-Path $P) -and ((Get-Item $P).Length -gt 0)) {
        Write-Host "  [OK] $f"
    } else {
        Write-Host "  [FAIL] $f MISSING"
    }
}
Write-Host ""

Write-Host "-- scheduled tasks --"
foreach ($t in "PatronAI-Heartbeat","PatronAI-Scan") {
    $task = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if ($task) {
        $info = $task | Get-ScheduledTaskInfo
        Write-Host ("  [OK] $t - State: " + $task.State + " - LastRun: " + $info.LastRunTime)
    } else {
        Write-Host "  [FAIL] $t NOT REGISTERED"
    }
}
Write-Host ""

Write-Host "-- last 20 entries in agent.log --"
if (Test-Path $Log) {
    Get-Content $Log -Tail 20 | ForEach-Object { Write-Host ("  " + $_) }
} else {
    Write-Host "  agent.log missing - agent has never run, or log was deleted."
}
Write-Host ""

Write-Host "-- live PUT probe (heartbeat URL) --"
$UrlFile = Join-Path $AgentDir "heartbeat_url.txt"
if (Test-Path $UrlFile) {
    $HbUrl = (Get-Content $UrlFile).Trim()
    $Body  = '{"event_type":"DIAGNOSTIC_PROBE","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ") + '"}'
    try {
        $Resp = Invoke-WebRequest -Uri $HbUrl -Method Put -Body $Body `
                -ContentType "application/json" -TimeoutSec 15 -UseBasicParsing
        Write-Host ("  HTTP " + $Resp.StatusCode + " from heartbeat URL")
        if ($Resp.StatusCode -eq 200 -or $Resp.StatusCode -eq 201) {
            Write-Host "  [OK] S3 accepted the PUT - auth + network OK"
        }
    } catch {
        $Code = 0
        if ($_.Exception.Response) { $Code = [int]$_.Exception.Response.StatusCode }
        Write-Host ("  HTTP " + $Code + " - " + $_.Exception.Message)
        if ($Code -eq 403)        { Write-Host "  [FAIL] 403 - presigned URL likely EXPIRED. Re-issue installer." }
        elseif ($Code -eq 0)      { Write-Host "  [FAIL] network unreachable - corporate firewall / DNS / VPN issue" }
    }
} else {
    Write-Host "  [FAIL] heartbeat_url.txt not found"
}
Write-Host ""
Write-Host "============================================="
Write-Host "Send this output back to IT if anything is [FAIL]."
