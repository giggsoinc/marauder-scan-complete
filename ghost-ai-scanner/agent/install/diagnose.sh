#!/usr/bin/env bash
# =============================================================
# FILE: ~/.patronai/diagnose.sh   (after install — installer copies this here)
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: One-command self-test for hook-agent recipients.
#          Prints config snapshot + last 50 agent.log lines + a
#          live PUT probe so IT can answer "is my agent working?"
#          without remote-debugging the laptop.
# USAGE:   bash ~/.patronai/diagnose.sh
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Step 0 — local diagnostics.
# =============================================================
set -u

AGENT_DIR="$HOME/.patronai"
CFG="$AGENT_DIR/config.json"
LOG="$AGENT_DIR/agent.log"

echo "PatronAI agent — diagnostic report"
echo "============================================="
date -u +"now: %Y-%m-%dT%H:%M:%SZ"
echo

if [ ! -f "$CFG" ]; then
  echo "✗ Config not found at $CFG. Agent may not be installed."
  exit 1
fi

echo "── identity (config.json) ──"
python3 - <<PY
import json
c = json.load(open("$CFG"))
for k in ("token","email","device_uuid","mac_primary","company","bucket","region"):
    print(f"  {k:14s}: {c.get(k,'')}")
PY
echo

echo "── current local IPs ──"
python3 -c "import socket; print('  ' + ', '.join(sorted({i for i in socket.gethostbyname_ex(socket.gethostname())[2] if not i.startswith('127.')})))" 2>/dev/null

echo
echo "── URL files present? ──"
for f in heartbeat_url scan_url authorized_url urls_refresh_url; do
  if [ -f "$AGENT_DIR/$f" ] && [ -s "$AGENT_DIR/$f" ]; then
    echo "  ✓ $f"
  else
    echo "  ✗ $f MISSING"
  fi
done

echo
echo "── last 20 entries in agent.log ──"
if [ -f "$LOG" ]; then
  tail -n 20 "$LOG" | sed 's/^/  /'
else
  echo "  agent.log missing — agent has never run, or log was deleted."
fi

echo
echo "── live PUT probe (heartbeat URL) ──"
if [ -f "$AGENT_DIR/heartbeat_url" ]; then
  HB=$(cat "$AGENT_DIR/heartbeat_url")
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
        -X PUT "$HB" -H 'Content-Type: application/json' \
        -d '{"event_type":"DIAGNOSTIC_PROBE","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}')
  echo "  HTTP $HTTP from heartbeat URL"
  case "$HTTP" in
    200|201) echo "  ✓ S3 accepted the PUT — auth + network OK" ;;
    403)     echo "  ✗ 403 — presigned URL likely EXPIRED. Re-issue installer." ;;
    000)     echo "  ✗ network unreachable — corporate firewall / DNS / VPN issue" ;;
    *)       echo "  ✗ unexpected. Send this report to your admin." ;;
  esac
fi
echo
echo "============================================="
echo "Send this output back to IT if anything is ✗."
